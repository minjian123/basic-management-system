"""租户管理服务（列表 / 详情 / 修改 / 停用 / 启用 / 注销 / 恢复 + 事件；任务 `04_01` / `04_03`）。

- 数据访问：`sys_tenant` / `sys_tenant_database` / `sys_tenant_module` / `sys_tenant_quota`（tenant 服务平台库）。
- 边界：平台租户（`kind = platform`）不参与业务租户列表，且禁止停用 / 修改（只经引导维护）。
- 事件：`tenant.created/suspended/activated/deleted` 经 Outbox 与状态变更同事务。
- **注销（04_03）**：只置 `deleted` + 记保留期时点、**不删数据**（恢复窗口内数据必须还在）；
  物理清理与 `tenant.purged` 由清理作业（子任务 `-02`）负责。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    TenantAdminNotFoundError,
    TenantDeleteConfirmError,
    TenantDomainConflictError,
    TenantRetentionClosedError,
    TenantStateConflictError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.plugin import NULL_PLUGIN_NAME
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.models.tenant.tenant import (
    TENANT_KIND_PLATFORM,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_DELETED,
    TENANT_STATUS_SUSPENDED,
    SysTenant,
)
from bms_core.outbox.base import BaseOutboxStore
from bms_tenant.domains.tenant.repositories.tenant_registry import TenantRegistryRepository
from bms_tenant.domains.tenant.schemas.tenant_admin import (
    TenantDeleteRequest,
    TenantDetail,
    TenantList,
    TenantListItem,
    TenantStatus,
    TenantUpdateRequest,
)
from bms_tenant.domains.tenant.services.tenant_module import TenantModuleService
from bms_tenant.domains.tenant.services.tenant_quota import TenantQuotaService

__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "DELETION_RETENTION_KEY",
    "TenantAdminService",
    "parse_retention_days",
]

DELETION_RETENTION_KEY = "tenant.deletion.retention_days"
"""保留期系统参数键（`sys_config`；改配置即时生效，无需重启）。"""

DEFAULT_RETENTION_DAYS = 30
"""保留期缺省天数（参数缺失 / 非法时回落）。"""

_LOGGER = get_logger("bms.tenant_admin")


class TenantAdminService(BaseFrameworkObject):
    """租户管理服务（会话绑定；事务边界由调用方负责）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        modules: TenantModuleService,
        quotas: TenantQuotaService,
        outbox: BaseOutboxStore,
        config: BaseConfigSource | None = None,
        settings: Settings | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（写）。
            modules: 租户模块服务。
            quotas: 租户配额服务。
            outbox: 事务性发件箱。
            config: 系统参数取数（保留期）；None 用缺省 30 天。
            settings: 应用配置（判归档能力是否就绪）；None 视为未就绪（`purge_at` 留空）。
        """
        self._session = session
        self._repo = TenantRegistryRepository(session)
        self._modules = modules
        self._quotas = quotas
        self._outbox = outbox
        self._config = config
        self._settings = settings

    async def list(
        self,
        *,
        page: int,
        size: int,
        code: str | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> TenantList:
        """分页取业务租户。

        Args:
            page: 页码。
            size: 每页条数。
            code: 编码模糊筛选。
            name: 名称模糊筛选。
            status: 状态筛选。

        Returns:
            TenantList: 分页结果。
        """
        rows, total = await self._repo.page_business(page=page, size=size, code=code, name=name, status=status)
        items = ConcurrentStableList[TenantListItem]()
        for row in rows:
            module_rows = await self._modules.list_items(int(row.id))
            items.add(
                TenantListItem(
                    id=int(row.id),
                    code=row.code,
                    name=row.name,
                    domain=row.domain,
                    status=_status(row),
                    expire_at=row.expire_at,
                    purge_at=row.purge_at,
                    modules=ConcurrentStableList(item.module_key for item in module_rows if item.status == "enabled"),
                    created_at=row.created_at,
                    version=int(row.version),
                )
            )
        return TenantList(list=items, total=total, page=page, size=size)

    async def detail(self, tenant_id: int) -> TenantDetail:
        """取租户详情（含配额与模块清单）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 租户详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        row = await self._require(tenant_id)
        return TenantDetail(
            id=int(row.id),
            code=row.code,
            name=row.name,
            domain=row.domain,
            status=_status(row),
            expire_at=row.expire_at,
            deletion_requested_at=row.deletion_requested_at,
            purge_at=row.purge_at,
            quotas=await self._quotas.list_items(int(row.id)),
            modules=await self._modules.list_items(int(row.id)),
            created_at=row.created_at,
            updated_at=row.updated_at,
            version=int(row.version),
        )

    async def update(self, tenant_id: int, req: TenantUpdateRequest) -> TenantDetail:
        """修改租户（名称 / 域名 / 到期时间）。

        Args:
            tenant_id: 租户主键。
            req: 修改请求。

        Returns:
            TenantDetail: 更新后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户不可修改（82003 / 409）。
            TenantDomainConflictError: 域名冲突（82004 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        domain = req.domain.strip().lower() if req.domain else None
        if (
            domain is not None
            and domain != row.domain
            and await self._repo.domain_taken(domain, exclude_id=int(row.id))
        ):
            raise TenantDomainConflictError(f"租户域名已被占用：{domain}")
        await self._repo.update_fields(row, name=req.name, domain=domain, expire_at=req.expire_at)
        await self._session.commit()
        return await self.detail(tenant_id)

    async def suspend(self, tenant_id: int) -> TenantDetail:
        """停用租户（置 `suspended` + 事件；引擎回收与会话撤销由 API 编排）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 停用后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不允许（82003 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status != TENANT_STATUS_ACTIVE:
            raise TenantStateConflictError(f"租户状态不允许停用：{row.status}")
        row.status = TENANT_STATUS_SUSPENDED
        await self._session.flush()
        await self.enqueue_event(row, "tenant.suspended")
        await self._session.commit()
        return await self.detail(tenant_id)

    async def activate(self, tenant_id: int) -> TenantDetail:
        """启用租户（置 `active` + 事件）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 启用后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不允许（82003 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status != TENANT_STATUS_SUSPENDED:
            raise TenantStateConflictError(f"租户状态不允许启用：{row.status}")
        row.status = TENANT_STATUS_ACTIVE
        await self._session.flush()
        await self.enqueue_event(row, "tenant.activated")
        await self._session.commit()
        return await self.detail(tenant_id)

    async def delete(self, tenant_id: int, req: TenantDeleteRequest) -> TenantDetail:
        """注销租户（置 `deleted` + 保留期时点 + 事件；**不删数据**，引擎回收与会话撤销由 API 编排）。

        Args:
            tenant_id: 租户主键。
            req: 注销请求（确认码须等于租户编码 + 可选原因）。

        Returns:
            TenantDetail: 注销后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不允许（82003 / 409）。
            TenantDeleteConfirmError: 确认码不匹配（82014 / 400）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status not in (TENANT_STATUS_ACTIVE, TENANT_STATUS_SUSPENDED):
            raise TenantStateConflictError(f"租户状态不允许注销：{row.status}")
        if req.confirm_code.strip() != row.code:
            raise TenantDeleteConfirmError("注销确认码与租户编码不一致")
        now = _now()
        purge_at = await self._purge_at(now)
        await self._repo.set_deleted(row, requested_at=now, purge_at=purge_at)
        extra: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        if purge_at is not None:
            extra.set("purge_at", _iso(purge_at))
        if req.reason:
            extra.set("reason", req.reason.strip())
        await self.enqueue_event(row, "tenant.deleted", extra=extra)
        await self._session.commit()
        return await self.detail(tenant_id)

    async def restore(self, tenant_id: int) -> TenantDetail:
        """恢复注销租户（保留期内；过期拒绝）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TenantDetail: 恢复后的详情。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
            TenantStateConflictError: 平台租户 / 状态不是 `deleted`（82003 / 409）。
            TenantRetentionClosedError: 已过保留期（82015 / 409）。
        """
        row = await self._require(tenant_id)
        _ensure_business(row)
        if row.status != TENANT_STATUS_DELETED:
            raise TenantStateConflictError(f"租户状态不允许恢复：{row.status}")
        if row.purge_at is not None and row.purge_at <= _now():
            raise TenantRetentionClosedError("保留期已过，不可恢复（需运维介入并留审计）")
        await self._repo.restore(row)
        await self.enqueue_event(row, "tenant.activated")
        await self._session.commit()
        return await self.detail(tenant_id)

    async def tenant_row(self, tenant_id: int) -> SysTenant:
        """取注册行（供 API 编排引擎回收 / 会话撤销）。

        Args:
            tenant_id: 租户主键。

        Returns:
            SysTenant: 注册行。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        return await self._require(tenant_id)

    async def enqueue_event(
        self, row: SysTenant, event_type: str, *, extra: ConcurrentStableDict[str, object] | None = None
    ) -> None:
        """发布租户生命周期事件（Outbox，与状态变更同事务）。

        Args:
            row: 注册行。
            event_type: 事件类型（`tenant.created` / `suspended` / `activated` / `deleted`）。
            extra: 事件专属附加字段（如 `deleted` 的 `purge_at` / `reason`）。
        """
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "tenant_id": str(row.id),
                "db_key": await self._repo.db_basis(int(row.id)) or row.code,
                "status": row.status,
                # 版本戳：消费侧业务级幂等键的第三段（`tenant_id + 事件类型 + version`）。
                "version": int(row.version),
            }
        )
        for key, value in (extra or {}).items():
            payload.set(key, value)
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=event_type,
                payload=payload,
                tenant_id=str(row.id),
                aggregate_key=row.code,
            ),
        )

    async def _retention_days(self) -> int:
        """取保留期天数（`sys_config` 键，缺失 / 非法回落缺省 30）。

        Returns:
            int: 保留期天数（恒 > 0）。
        """
        if self._config is None:
            return DEFAULT_RETENTION_DAYS
        return parse_retention_days(await self._config.get(DELETION_RETENTION_KEY, str(DEFAULT_RETENTION_DAYS)))

    async def _purge_at(self, now: datetime) -> datetime | None:
        """算保留期截止；归档能力未就绪时留空（由清理扫描回填，不阻塞注销）。

        Args:
            now: 注销申请时刻（UTC）。

        Returns:
            datetime | None: 保留期截止（UTC）；归档未就绪时为 None。
        """
        if not self._archive_ready():
            _LOGGER.info("tenant_archive_not_ready", hint="归档执行器未就绪，purge_at 留空待回填")
            return None
        return now + timedelta(days=await self._retention_days())

    def _archive_ready(self) -> bool:
        """归档能力是否就绪（provider 为空 / null 即未就绪）。

        Returns:
            bool: 就绪为 True。
        """
        if self._settings is None:
            return False
        provider = self._settings.archive_policy.provider
        return provider not in ("", NULL_PLUGIN_NAME)

    async def _require(self, tenant_id: int) -> SysTenant:
        """取注册行或抛 82002。

        Args:
            tenant_id: 租户主键。

        Returns:
            SysTenant: 注册行。

        Raises:
            TenantAdminNotFoundError: 不存在（82002 / 404）。
        """
        row = await self._repo.by_id(tenant_id)
        if row is None:
            raise TenantAdminNotFoundError("租户不存在或已删除")
        return row


def parse_retention_days(raw: str | None) -> int:
    """解析保留期天数（缺失 / 非整数 / 非正数回落缺省 30 并告警，不阻断注销或清理）。

    Args:
        raw: 参数原文（`sys_config` 值）。

    Returns:
        int: 保留期天数（恒 > 0）。
    """
    if raw is None:
        return DEFAULT_RETENTION_DAYS
    try:
        days = int(raw)
    except ValueError:
        _LOGGER.warning("tenant_retention_invalid", value=raw, fallback=DEFAULT_RETENTION_DAYS)
        return DEFAULT_RETENTION_DAYS
    if days <= 0:
        _LOGGER.warning("tenant_retention_invalid", value=raw, fallback=DEFAULT_RETENTION_DAYS)
        return DEFAULT_RETENTION_DAYS
    return days


def _now() -> datetime:
    """当前 UTC 时刻（与库内 DATETIME 同口径：naive UTC）。

    Returns:
        datetime: 当前 UTC 时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    """UTC 时刻 → ISO8601 字符串（事件载荷只放标量；跨语言稳定）。

    Args:
        value: UTC 时刻（naive）。

    Returns:
        str: `YYYY-MM-DDTHH:MM:SSZ`。
    """
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _status(row: SysTenant) -> TenantStatus:
    """注册行状态 → 契约状态。

    Args:
        row: 注册行。

    Returns:
        TenantStatus: 契约状态。
    """
    return cast("TenantStatus", row.status)


def _ensure_business(row: SysTenant) -> None:
    """平台租户不允许停用 / 修改（只经引导维护）。

    Args:
        row: 注册行。

    Raises:
        TenantStateConflictError: 平台租户（82003 / 409）。
    """
    if row.kind == TENANT_KIND_PLATFORM:
        raise TenantStateConflictError("平台租户不可停用或修改（只经平台引导维护）")
