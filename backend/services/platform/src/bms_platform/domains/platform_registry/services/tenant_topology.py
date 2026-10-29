"""租户拓扑服务（07C `02_01`）：校验、整批写入与生效、自举、快照装载、导出。

口径（详细设计 §3）：

- **整批替换**：一次写入替换某租户当前版本（软删旧行 + 插新行），同批次同一 `topology_version`；
  解析永远看到完整版本，不存在「一半新一半旧」的中间态；
- **写入即生效**：写入后在同进程内登记新快照（`(租户, 版本)` 键），无需广播；
- **默认拓扑自举**：`tenant_id=0` 无记录时按「已登记域 → 该域承载服务键」写入版本 1——与 07B 过渡
  实现行为等价（库名零变化），且满足「拓扑缺失即拒启」；
- **校验七条**：域已登记 / 单元命名 / 同域唯一 / 非空 / 默认拓扑覆盖全部域 / 模板名合法 / 版本递增；
- **审计**：整批替换记一条（租户、版本、域数、来源），不逐行记。
"""

import re
from collections.abc import Iterable

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.collaboration.topology import (
    DEFAULT_TOPOLOGY_TENANT,
    TOPOLOGY_ENTRY_DISABLED,
    TOPOLOGY_ENTRY_ENABLED,
    TopologyEntry,
    TopologySnapshot,
    register_topology_snapshot,
)
from bms_core.collaboration.topology_templates import TEMPLATES, expand_template
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import CatalogError, ConflictError, NotFoundError, ParamError
from bms_core.db.session import DbSession
from bms_core.models.platform.tenant_topology import (
    TOPOLOGY_STATUS_ENABLED,
    TOPOLOGY_STATUSES,
    SysTenantTopology,
)
from bms_core.schemas.pagination import BasePageQuery
from bms_core.services.module_registry import domain_service_view
from bms_platform.domains.platform_registry.repositories.tenant_topology import (
    TenantTopologyRepository,
)

__all__ = ["TenantTopologyService", "TopologyRow"]

_TABLE = "sys_tenant_topology"
_UNIT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,63}$")

_TEMPLATE_NOTE_PREFIX = "模板："
"""模板展开写入时的说明前缀（`note` 留痕来源）。"""

_DEFAULT_NOTE = "启动自举：域 → 承载服务"
"""默认拓扑自举写入的说明。"""


class TopologyRow:
    """待写入的一行（校验前的中间形态；不对外暴露）。"""

    def __init__(self, domain_key: str, unit_key: str, status: str = TOPOLOGY_STATUS_ENABLED, note: str = "") -> None:
        """初始化。

        Args:
            domain_key: 业务域标识。
            unit_key: 部署单元标识。
            status: 状态（enabled / disabled）。
            note: 说明。
        """
        self.domain_key = domain_key
        self.unit_key = unit_key
        self.status = status
        self.note = note


class TenantTopologyService:
    """租户拓扑服务（校验 / 写入 / 自举 / 快照 / 导出）。"""

    def __init__(self, session: DbSession, *, audit: AuditCapturer | None = None) -> None:
        """初始化。

        Args:
            session: 平台库会话（写路径由调用方经工作单元提交）。
            audit: 审计捕获器（可选；缺省不留痕，便于只读场景复用）。
        """
        self._repo = TenantTopologyRepository(session)
        self._audit = audit

    async def page(
        self,
        query: BasePageQuery,
        *,
        tenant_id: int | None = None,
        domain_key: str | None = None,
        unit_key: str | None = None,
    ) -> tuple[ConcurrentStableList[SysTenantTopology], int]:
        """分页查询当前版本行。

        Args:
            query: 分页请求。
            tenant_id: 租户筛选。
            domain_key: 业务域筛选。
            unit_key: 部署单元筛选。

        Returns:
            tuple[ConcurrentStableList[SysTenantTopology], int]: (当前页, 总数)。
        """
        return await self._repo.page_rows(query, tenant_id=tenant_id, domain_key=domain_key, unit_key=unit_key)

    async def export(self, tenant_id: int) -> tuple[int, ConcurrentStableList[SysTenantTopology]]:
        """按租户导出当前版本（部署编排输入）。

        Args:
            tenant_id: 租户主键。

        Returns:
            tuple[int, ConcurrentStableList[SysTenantTopology]]: (版本, 当前版本行；无记录时版本 0)。

        Raises:
            NotFoundError: 该租户与默认拓扑都没有记录（10002）。
        """
        rows = await self._repo.list_current(tenant_id)
        if rows:
            return rows[0].topology_version, rows
        if tenant_id == DEFAULT_TOPOLOGY_TENANT:
            raise NotFoundError(f"租户 {tenant_id} 尚无部署拓扑记录")
        version = await self._repo.current_version(DEFAULT_TOPOLOGY_TENANT)
        if version == 0:
            raise NotFoundError(f"租户 {tenant_id} 尚无部署拓扑记录，且默认拓扑未自举")
        default_rows = await self._repo.list_current(DEFAULT_TOPOLOGY_TENANT)
        return version, default_rows

    async def replace(
        self,
        tenant_id: int,
        *,
        rows: Iterable[TopologyRow] | None = None,
        template: str | None = None,
        version: int | None = None,
        note: str = "",
        actor: int | None = None,
    ) -> tuple[int, ConcurrentStableList[SysTenantTopology]]:
        """整批替换某租户的拓扑（`rows` 与 `template` 二选一）。

        Args:
            tenant_id: 租户主键（`0` 为默认拓扑）。
            rows: 整批行（人工指定）。
            template: 模板名（按已登记域展开）。
            version: 目标版本（空=当前版本+1；须递增）。
            note: 本批次说明。
            actor: 操作人（缺省取当前登录用户）。

        Returns:
            tuple[int, ConcurrentStableList[SysTenantTopology]]: (生效版本, 新版本行)。

        Raises:
            ParamError: 参数非法（两者都空 / 都给 / 域未登记 / 单元命名非法 / 空拓扑 / 未知模板 /
                默认拓扑未覆盖全部域 / 状态非法）（10001）。
            ConflictError: 同域重复或版本回退（10003）。
        """
        entries = self._entries(rows=rows, template=template, note=note)
        domains = domain_service_view()
        self._validate(tenant_id, entries=entries, domains=domains)
        current = await self._repo.current_version(tenant_id)
        if version is not None and version <= current:
            raise ConflictError(f"拓扑版本须递增：当前 {current}，请求 {version}")
        target_version = version or current + 1
        orm_rows = ConcurrentStableList(
            SysTenantTopology(
                tenant_id=tenant_id,
                domain_key=entry.domain_key,
                unit_key=entry.unit_key,
                topology_version=target_version,
                status=entry.status,
                note=entry.note or None,
                created_by=actor if actor is not None else current_user_id.get(),
            )
            for entry in entries
        )
        await self._repo.replace(tenant_id, version=target_version, rows=orm_rows)
        self._register_snapshot(tenant_id, target_version, entries)
        self._capture(tenant_id, version=target_version, previous=current, entries=entries, actor=actor)
        return target_version, await self._repo.list_current(tenant_id)

    async def ensure_default(self, *, actor: int | None = None) -> int:
        """确保默认拓扑存在（无则按「域 → 承载服务键」自举版本 1）。

        Args:
            actor: 操作人（启动期为空）。

        Returns:
            int: 默认拓扑当前版本。

        Raises:
            CatalogError: 业务域登记为空（无法自举；属装配错误，拒启）。
        """
        version = await self._repo.current_version(DEFAULT_TOPOLOGY_TENANT)
        if version > 0:
            snapshot = await self._snapshot_of(DEFAULT_TOPOLOGY_TENANT)
            if snapshot is not None:
                register_topology_snapshot(snapshot)
            return version
        domains = domain_service_view()
        if not domains:
            raise CatalogError("业务域登记为空，无法自举默认拓扑（请检查清单第九类 [[domains]] 装载）")
        entries = ConcurrentStableList(
            TopologyRow(domain_key=domain, unit_key=service, note=_DEFAULT_NOTE) for domain, service in domains.items()
        )
        target_version, _ = await self.replace(
            DEFAULT_TOPOLOGY_TENANT, rows=entries, version=1, note=_DEFAULT_NOTE, actor=actor
        )
        return target_version

    async def snapshot(self) -> ConcurrentStableList[TopologySnapshot]:
        """装载全部租户当前版本的快照（启动钩子用）。

        Returns:
            ConcurrentStableList[TopologySnapshot]: 各租户快照（至少含默认拓扑时才有内容）。
        """
        rows = await self._repo.list_current_all()
        grouped: ConcurrentStableDict[int, ConcurrentStableDict[str, TopologyEntry]] = ConcurrentStableDict()
        versions: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        for row in rows:
            entries: ConcurrentStableDict[str, TopologyEntry] | None = grouped.get(row.tenant_id)
            if entries is None:
                entries = ConcurrentStableDict()
                grouped.set(row.tenant_id, entries)
            entries.set(
                row.domain_key,
                TopologyEntry(
                    unit_key=row.unit_key,
                    status=TOPOLOGY_ENTRY_ENABLED if row.status == TOPOLOGY_STATUS_ENABLED else TOPOLOGY_ENTRY_DISABLED,
                ),
            )
            versions.set(row.tenant_id, row.topology_version)
        return ConcurrentStableList(
            TopologySnapshot(
                tenant_id=tenant_id,
                version=versions.get(tenant_id, 0),
                entries=ConcurrentStableFrozenDict(entries.to_list()),
            )
            for tenant_id, entries in grouped.items()
        )

    async def _snapshot_of(self, tenant_id: int) -> TopologySnapshot | None:
        """取单租户当前版本快照（自举后登记用）。

        Args:
            tenant_id: 租户主键。

        Returns:
            TopologySnapshot | None: 快照；无记录返回 None。
        """
        rows = await self._repo.list_current(tenant_id)
        if not rows:
            return None
        return TopologySnapshot(
            tenant_id=tenant_id,
            version=rows[0].topology_version,
            entries=ConcurrentStableFrozenDict(
                (
                    row.domain_key,
                    TopologyEntry(
                        unit_key=row.unit_key,
                        status=TOPOLOGY_ENTRY_ENABLED
                        if row.status == TOPOLOGY_STATUS_ENABLED
                        else TOPOLOGY_ENTRY_DISABLED,
                    ),
                )
                for row in rows
            ),
        )

    def _entries(
        self, *, rows: Iterable[TopologyRow] | None, template: str | None, note: str
    ) -> ConcurrentStableList[TopologyRow]:
        """按 `rows` / `template` 归一为待写入行（二选一）。

        Args:
            rows: 人工指定的整批行。
            template: 模板名。
            note: 本批次说明（模板展开时并入行说明）。

        Returns:
            ConcurrentStableList[TopologyRow]: 待写入行。

        Raises:
            ParamError: 两者都空或都给，或模板名未知（10001）。
        """
        if template is not None:
            if rows is not None:
                raise ParamError("rows 与 template 只能二选一")
            expanded = expand_template(template, domain_service_view().keys())
            suffix = note or f"{_TEMPLATE_NOTE_PREFIX}{template}"
            return ConcurrentStableList(
                TopologyRow(domain_key=item.domain_key, unit_key=item.unit_key, note=suffix) for item in expanded
            )
        if rows is None:
            raise ParamError(f"必须提供 rows 或 template（可选 {' / '.join(TEMPLATES)}）")
        items = ConcurrentStableList(rows)
        if note:
            for item in items:
                if not item.note:
                    item.note = note
        return items

    @staticmethod
    def _validate(
        tenant_id: int,
        *,
        entries: ConcurrentStableList[TopologyRow],
        domains: ConcurrentStableDict[str, str],
    ) -> None:
        """校验（设计 §3.4 的第 1~5 条与状态合法性）。

        Args:
            tenant_id: 租户主键。
            entries: 待写入行。
            domains: 已登记业务域视图。

        Raises:
            ParamError: 域未登记 / 单元命名非法 / 空拓扑 / 状态非法 / 默认拓扑未覆盖全部域（10001）。
            ConflictError: 同域重复（10003）。
        """
        if not entries:
            raise ParamError("拓扑不得为空（每个部署单元至少要承载一个业务域）")
        unknown = ConcurrentStableList(entry.domain_key for entry in entries if entry.domain_key not in domains)
        if unknown:
            raise ParamError(f"拓扑引用了未登记的业务域：{', '.join(unknown)}")
        bad_units = ConcurrentStableList(entry.unit_key for entry in entries if not _UNIT_PATTERN.match(entry.unit_key))
        if bad_units:
            raise ParamError(f"部署单元命名非法（应匹配 ^[a-z][a-z0-9-]*$）：{', '.join(bad_units)}")
        bad_status = ConcurrentStableList(entry.status for entry in entries if entry.status not in TOPOLOGY_STATUSES)
        if bad_status:
            raise ParamError(f"拓扑状态非法：{', '.join(bad_status)}")
        seen: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        duplicates: ConcurrentStableList[str] = ConcurrentStableList()
        for entry in entries:
            count = seen.get(entry.domain_key, 0) + 1
            seen.set(entry.domain_key, count)
            if count == 2:
                duplicates.add(entry.domain_key)
        if duplicates:
            raise ConflictError(f"同一业务域在同一租户内只能映射一个部署单元：{', '.join(duplicates)}")
        if tenant_id == DEFAULT_TOPOLOGY_TENANT:
            missing = ConcurrentStableList(domain for domain in domains if domain not in seen)
            if missing:
                raise ParamError(f"默认拓扑必须覆盖全部已登记业务域，缺少：{', '.join(missing)}")

    @staticmethod
    def _register_snapshot(tenant_id: int, version: int, entries: ConcurrentStableList[TopologyRow]) -> None:
        """把新版本写入进程内快照（写入即生效）。

        Args:
            tenant_id: 租户主键。
            version: 版本号。
            entries: 新版本行。
        """
        register_topology_snapshot(
            TopologySnapshot(
                tenant_id=tenant_id,
                version=version,
                entries=ConcurrentStableFrozenDict(
                    (entry.domain_key, TopologyEntry(unit_key=entry.unit_key, status=entry.status)) for entry in entries
                ),
            )
        )

    def _capture(
        self,
        tenant_id: int,
        *,
        version: int,
        previous: int,
        entries: ConcurrentStableList[TopologyRow],
        actor: int | None,
    ) -> None:
        """写审计留痕（整批替换一条）。

        Args:
            tenant_id: 租户主键。
            version: 新版本。
            previous: 变更前版本。
            entries: 新版本行。
            actor: 操作人（启动期为空）。
        """
        if self._audit is None:
            return
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
            (
                FieldChange(field="topology_version", old=previous, new=version),
                FieldChange(field="domains", old=None, new=len(entries)),
            )
        )
        self._audit.capture(
            table=_TABLE,
            model_id=tenant_id,
            changes=changes,
            actor=actor if actor is not None else current_user_id.get(),
        )
