"""能力分配授权服务（07B `02_04`）：声明同步、人工授予 / 撤销、派生视图与审计。

口径（详见任务 `02_04` 详细设计）：

- **两层来源**：产品声明的 `default_consumers` 是基线（`source=declared`），平台管理面人工授予 /
  撤销是覆盖（`source=manual`）——人工介入过的记录，声明装载不再改动；
- **声明回归**：曾因「声明移除」被禁用的记录，声明重新出现时恢复有效（`note` 复位为默认说明）；
- **撤销不删行**：只切 `status` + `revoked_at`，保留授权历史；
- **写校验**：能力须已登记、消费方须为已登记服务键或产品键、临时授权的有效期与理由成对；
- **审计**：授予 / 撤销 / 声明装载的状态变更均经 `AuditCapturer.capture`（当前为占位实现，
  真实落库归 29-审计合规）；
- **派生刷新**：每次变更后清授权视图快照（`invalidate_capability_grants`）并刷新有效授权数指标。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.collaboration.grant import (
    METRIC_CAPABILITY_GRANT_ACTIVE,
    CapabilityGrant,
    declare_capability_grants,
    invalidate_capability_grants,
    is_grant_effective,
    plan_grant_sync,
)
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import ConfigError, NotFoundError, ParamError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.metrics.base import BaseMetrics
from bms_core.models.platform.capability_grant import (
    GRANT_NOTE_DECLARED,
    GRANT_SOURCE_MANUAL,
    GRANT_STATUS_DISABLED,
    GRANT_STATUS_ENABLED,
    SysCapabilityGrant,
)
from bms_core.schemas.pagination import BasePageQuery
from bms_core.services.module_registry import (
    collaboration_catalog_view,
    product_keys,
    service_catalog_view,
)
from bms_platform.domains.platform_registry.repositories.capability_grant import (
    CapabilityGrantRepository,
)

__all__ = ["CapabilityGrantService", "GrantSyncReport"]

_TABLE = "sys_capability_grant"
"""审计逻辑表名。"""

_LOGGER = get_logger("bms.platform.capability_grant")


@dataclass(frozen=True)
class GrantSyncReport(BaseValueObject):
    """声明同步报告（逐项计数 + 警示；供启动日志与运维核对）。"""

    created: int = 0
    """新建的声明记录数。"""

    restored: int = 0
    """恢复为有效的声明记录数（声明回归）。"""

    revoked: int = 0
    """因声明移除而撤销的记录数。"""

    warnings: ConcurrentStableFrozenList[str] = dataclass_field(
        default_factory=lambda: ConcurrentStableFrozenList[str]()
    )
    """声明与人工不一致等警示（不静默择一）。"""

    @property
    def changed(self) -> bool:
        """本次同步是否产生变更。

        Returns:
            bool: 有变更为 True。
        """
        return bool(self.created or self.restored or self.revoked)


class CapabilityGrantService(BaseFrameworkObject):
    """能力分配授权服务（事务边界在本层；仓储只 flush）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        audit: AuditCapturer | None = None,
        metrics: BaseMetrics | None = None,
        uow: DbUnitOfWork | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（读走只读会话、写走主库会话）。
            audit: 审计捕获器（None 表示不写审计——仅授权视图读取路径使用）。
            metrics: 指标器（None 表示不记录；有效授权数 gauge 用）。
            uow: 平台库工作单元（写路径必填；只读查询可缺省）。
        """
        self._session = session
        self._audit = audit
        self._metrics = metrics
        self._uow = uow

    @property
    def _repo(self) -> CapabilityGrantRepository:
        """当前会话的授权仓储。

        Returns:
            CapabilityGrantRepository: 仓储实例。
        """
        return CapabilityGrantRepository(self._session)

    def _transaction(self) -> DbUnitOfWork:
        """取写路径工作单元（未注入即配置错误，不允许无事务直写）。

        Returns:
            DbUnitOfWork: 工作单元。

        Raises:
            ConfigError: 写路径未注入工作单元（装配错误）。
        """
        if self._uow is None:
            raise ConfigError("授权写路径缺少工作单元（请经 get_platform_uow 注入）")
        return self._uow

    @asynccontextmanager
    async def _write_scope(self) -> AsyncGenerator[None]:
        """写事务边界：先清掉只读查询遗留的空事务（autobegin），再统一开启写事务。

        服务内既有只读查询（分页 / 视图 / gauge 统计）会在会话上留下自动开启的事务；
        直接 `begin()` 会抛「事务已存在」。回滚空事务即可（无挂起写入，安全且幂等）。

        Yields:
            None: 事务运行期。
        """
        await self._session.rollback()
        async with self._transaction().begin():
            yield

    async def sync_declared(self) -> GrantSyncReport:
        """按产品声明同步默认授权（启动钩子调用；幂等）。

        Returns:
            GrantSyncReport: 同步报告（逐项计数 + 警示）。

        Raises:
            CatalogError: 授权视图来源 / 能力目录不可用（配置漂移，拒启级）。
        """
        declared = declare_capability_grants()
        async with self._write_scope():
            current = await self._current_grants()
            plan = plan_grant_sync(declared, current)
            for grant in plan.creates:
                row = await self._repo.create(
                    capability_name=grant.capability_name,
                    consumer_key=grant.consumer_key,
                    source=grant.source,
                    status=grant.status,
                    granted_at=datetime.now(UTC),
                    note=grant.note,
                )
                self._capture(row, old_status=None, actor=None)
            for grant in plan.restores:
                row = await self._repo.get_by_pair(grant.capability_name, grant.consumer_key)
                if row is None:  # pragma: no cover - 计划与现状同源（防御）
                    continue
                old_status = row.status
                row.status = GRANT_STATUS_ENABLED
                row.revoked_at = None
                row.note = GRANT_NOTE_DECLARED
                await self._repo.flush()
                self._capture(row, old_status=old_status, actor=None)
            for grant in plan.revokes:
                row = await self._repo.get_by_pair(grant.capability_name, grant.consumer_key)
                if row is None:  # pragma: no cover - 计划与现状同源（防御）
                    continue
                old_status = row.status
                row.status = GRANT_STATUS_DISABLED
                row.revoked_at = datetime.now(UTC)
                row.note = grant.note
                await self._repo.flush()
                self._capture(row, old_status=old_status, actor=None)
        for message in plan.warnings:
            _LOGGER.warning("capability_grant_manual_conflict", detail=message)
        report = GrantSyncReport(
            created=len(plan.creates),
            restored=len(plan.restores),
            revoked=len(plan.revokes),
            warnings=ConcurrentStableFrozenList(plan.warnings),
        )
        await self._after_change()
        return report

    async def grant(
        self,
        *,
        capability_name: str,
        consumer_key: str,
        expire_at: datetime | None = None,
        note: str = "",
        actor: int | None = None,
    ) -> SysCapabilityGrant:
        """人工授予（同一「能力 × 消费方」幂等 UPSERT；来源固定为人工）。

        Args:
            capability_name: 能力名（须已登记）。
            consumer_key: 消费方标识（须为已登记服务键或产品键）。
            expire_at: 有效期截止（UTC；None 表示长期有效）。
            note: 授予理由（临时授权必填）。
            actor: 操作人（`sys_user.id`）。

        Returns:
            SysCapabilityGrant: 授权记录。

        Raises:
            ParamError: 能力未登记 / 消费方未登记 / 有效期非法 / 临时授权缺理由（10001）。
        """
        name = capability_name.strip()
        consumer = consumer_key.strip()
        self._require_capability(name)
        self._require_consumer(consumer)
        reason = note.strip()
        moment = datetime.now(UTC)
        self._require_window(expire_at=expire_at, note=reason, now=moment)
        async with self._write_scope():
            row = await self._repo.get_by_pair(name, consumer)
            if row is None:
                row = await self._repo.create(
                    capability_name=name,
                    consumer_key=consumer,
                    source=GRANT_SOURCE_MANUAL,
                    status=GRANT_STATUS_ENABLED,
                    expire_at=expire_at,
                    granted_by=actor,
                    granted_at=moment,
                    note=reason or None,
                )
                self._capture(row, old_status=None, actor=actor)
            else:
                old_status = row.status
                row.source = GRANT_SOURCE_MANUAL
                row.status = GRANT_STATUS_ENABLED
                row.expire_at = expire_at
                row.granted_by = actor
                row.granted_at = moment
                row.revoked_at = None
                row.note = reason or None
                await self._repo.flush()
                self._capture(row, old_status=old_status, actor=actor)
        await self._after_change(provider_domain_of=name, consumer=consumer)
        return row

    async def revoke(self, grant_id: int, *, actor: int | None = None) -> SysCapabilityGrant:
        """撤销授权（软撤销：置 `disabled` + `revoked_at`，保留历史；重复撤销幂等）。

        Args:
            grant_id: 授权记录 ID。
            actor: 操作人（`sys_user.id`）。

        Returns:
            SysCapabilityGrant: 撤销后的记录。

        Raises:
            NotFoundError: 记录不存在（10002）。
        """
        async with self._write_scope():
            row = await self._repo.get(grant_id)
            if row is None:
                raise NotFoundError(f"授权记录不存在：{grant_id}")
            old_status = row.status
            row.status = GRANT_STATUS_DISABLED
            row.source = GRANT_SOURCE_MANUAL
            row.revoked_at = datetime.now(UTC)
            await self._repo.flush()
            if old_status != GRANT_STATUS_DISABLED:
                self._capture(row, old_status=old_status, actor=actor)
        await self._after_change(provider_domain_of=row.capability_name, consumer=row.consumer_key)
        return row

    async def page(
        self,
        query: BasePageQuery,
        *,
        capability_name: str | None = None,
        consumer_key: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> tuple[ConcurrentStableList[SysCapabilityGrant], int]:
        """分页查询授权记录（只读）。

        Args:
            query: 分页与排序请求。
            capability_name: 能力名筛选。
            consumer_key: 消费方筛选。
            status: 状态筛选。
            source: 来源筛选。

        Returns:
            tuple[ConcurrentStableList[SysCapabilityGrant], int]: (当前页记录, 总数)。
        """
        return await self._repo.page_grants(
            query,
            capability=capability_name,
            consumer=consumer_key,
            status=status,
            source=source,
        )

    async def view(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """取授权视图（`provider` 或 `consumer` 维度；二选一）。

        Args:
            provider: 提供方业务域（入站维度）。
            consumer: 消费方服务键（出站维度）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 该维度的启用记录（含已过期行，有效性由调用方判定）。

        Raises:
            ParamError: 两个维度都缺或都给出（10001）。
        """
        if (provider is None) == (consumer is None):
            raise ParamError("授权视图须且只须给出 provider 或 consumer 之一")
        if consumer is not None:
            rows = await self._repo.list_enabled_by_consumer(consumer)
        else:
            capabilities: ConcurrentStableList[str] = ConcurrentStableList()
            for record in collaboration_catalog_view():
                if record.domain == provider:
                    capabilities.add(record.name)
            rows = await self._repo.list_enabled_by_capabilities(capabilities)
        return ConcurrentStableList(_to_grant(row) for row in rows)

    async def _current_grants(self) -> ConcurrentStableList[CapabilityGrant]:
        """取库中现状（声明同步的差异基线）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 未软删记录。
        """
        rows = await self._repo.list_all()
        return ConcurrentStableList(_to_grant(row) for row in rows)

    async def _after_change(self, *, provider_domain_of: str | None = None, consumer: str | None = None) -> None:
        """变更后刷新派生（清视图快照 + 刷新有效授权数指标）。

        Args:
            provider_domain_of: 变更涉及的能力名（用于定位其提供方业务域失效）。
            consumer: 变更涉及的消费方（用于失效出站视图）。
        """
        if provider_domain_of is not None:
            for record in collaboration_catalog_view():
                if record.name == provider_domain_of:
                    invalidate_capability_grants(provider=record.domain)
                    break
        if consumer is not None:
            invalidate_capability_grants(consumer=consumer)
        await self._refresh_active_gauges()

    async def _refresh_active_gauges(self) -> None:
        """按能力刷新有效授权数（gauge；指标器缺省时跳过）。"""
        if self._metrics is None:
            return
        moment = datetime.now(UTC)
        counts: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for row in await self._repo.list_all():
            if not is_grant_effective(_to_grant(row), now=moment):
                continue
            counts.set(row.capability_name, counts.get(row.capability_name, 0) + 1)
        for capability, count in counts.items():
            labels: ConcurrentStableDict[str, str] = ConcurrentStableDict({"capability": capability})
            await self._metrics.gauge(METRIC_CAPABILITY_GRANT_ACTIVE, value=float(count), labels=labels)

    def _capture(self, row: SysCapabilityGrant, *, old_status: str | None, actor: int | None) -> None:
        """写审计留痕（状态变更）。

        Args:
            row: 授权记录。
            old_status: 变更前状态（新建为 None）。
            actor: 操作人（声明装载为 None）。
        """
        if self._audit is None:
            return
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
            [FieldChange(field="status", old=old_status, new=row.status)]
        )
        self._audit.capture(table=_TABLE, model_id=row.id, changes=changes, actor=actor)

    @staticmethod
    def _require_capability(capability: str) -> None:
        """校验收授能力已登记（能力视图为唯一判据）。

        Args:
            capability: 能力名。

        Raises:
            ParamError: 能力未登记（10001）。
        """
        for record in collaboration_catalog_view():
            if record.name == capability:
                return
        raise ParamError(f"能力未登记：{capability}（请检查产品清单 [[collaborations]] 与装载）")

    @staticmethod
    def _require_consumer(consumer: str) -> None:
        """校验消费方已登记（服务键 ∪ 产品键；前端应用不参与分配）。

        Args:
            consumer: 消费方标识。

        Raises:
            ParamError: 消费方未登记（10001）。
        """
        known: ConcurrentStableSet[str] = ConcurrentStableSet()
        known.update(product_keys())
        for record in service_catalog_view():
            if record.service_key:
                known.add(record.service_key)
            known.add(record.module_key)
        if consumer in known:
            return
        raise ParamError(f"消费方未登记：{consumer}（须为已登记服务键或产品键；前端应用不参与分配）")

    @staticmethod
    def _require_window(*, expire_at: datetime | None, note: str, now: datetime) -> None:
        """校验有效期与理由（临时授权两者成对）。

        Args:
            expire_at: 有效期截止（UTC）。
            note: 授予理由。
            now: 校验基准时刻。

        Raises:
            ParamError: 有效期不晚于当前时间，或临时授权缺理由（10001）。
        """
        if expire_at is None:
            return
        moment = expire_at if expire_at.tzinfo is not None else expire_at.replace(tzinfo=UTC)
        if moment <= now:
            raise ParamError("临时授权有效期必须晚于当前时间")
        if not note:
            raise ParamError("临时授权必须填写理由（note），避免长期留存的排障授权")


def _to_grant(row: SysCapabilityGrant) -> CapabilityGrant:
    """ORM 行 → 授权值对象。

    Args:
        row: 授权记录。

    Returns:
        CapabilityGrant: 值对象（`expire_at` 统一为 UTC 感知时间）。
    """
    expire_at = row.expire_at
    if expire_at is not None and expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=UTC)
    return CapabilityGrant(
        capability_name=row.capability_name,
        consumer_key=row.consumer_key,
        source=row.source,
        status=row.status,
        expire_at=expire_at,
        note=row.note or "",
    )
