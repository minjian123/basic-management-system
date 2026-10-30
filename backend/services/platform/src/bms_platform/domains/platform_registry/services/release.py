"""发布清单服务（07C `04_01`）：前置校验、清单写入、批次回滚与查询。

口径（详细设计 §3）：

- **发布单元 = 部署单元**：一次发布覆盖该单元承载的全部业务域，清单是**回滚的原子单位**；
- **先校验后执行**：§3.3 的六条校验逐项出结论，任一不过即整体失败且**不改变任何状态**
  （失败行只用于「执行阶段失败」留痕，不用于校验阶段）；
- **不可变**：发布行写入后不修改；回滚另起一行 `rolled_back`（`rolled_back_from` 指向被回滚清单），
  明细记录回退到的目标版本，历史始终可追溯；
- **不做第二份事实源**：版本事实仍在代码声明（服务目录）与各域版本记录表；清单只记发布结果快照，
  对账失败即失败，不双向同步；
- **结构回退需人工确认**：任一域结构 revision 需要回退即 `requires_confirmation`——删列类回退不可召回。
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ConfigError, ConflictError, NotFoundError, ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.migration import domain_series
from bms_core.db.session import DbSession
from bms_core.models.platform.release_manifest import (
    GLOBAL_TENANT_SCOPE,
    RELEASE_STATUS_FAILED,
    RELEASE_STATUS_RELEASED,
    RELEASE_STATUS_ROLLED_BACK,
    RELEASE_STATUSES,
    SysReleaseManifest,
    SysReleaseManifestDomain,
)
from bms_core.schemas.pagination import BasePageQuery
from bms_core.services.module_registry import ModuleRecord, domain_service_view, service_catalog_view
from bms_platform.domains.platform_registry.dto import (
    ReleaseCheckItem,
    ReleaseDomainEntry,
    ReleaseManifestSnapshot,
    ReleasePrecheckResult,
    RollbackPlan,
    RollbackStep,
)
from bms_platform.domains.platform_registry.ports import ContractBreachReader, ReleaseRevisionPort
from bms_platform.domains.platform_registry.repositories.release_manifest import (
    ReleaseManifestDomainRepository,
    ReleaseManifestRepository,
)
from bms_platform.domains.platform_registry.repositories.tenant_topology import TenantTopologyRepository

__all__ = ["ReleaseService"]

_TABLE = "sys_release_manifest"
"""审计落点（发布与回滚都记在本表上）。"""

_CHECK_UNIT_COMPLETE = "unit_complete"
_CHECK_VERSION = "version_consistent"
_CHECK_TOPOLOGY = "topology_current"
_CHECK_STRUCTURE = "structure_ready"
_CHECK_CONTRACT = "contract_compatible"
_CHECK_VERSION_MONOTONIC = "manifest_version_monotonic"

_TITLES: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    {
        _CHECK_UNIT_COMPLETE: "单元完整（单元所含域 = 拓扑该单元全部域）",
        _CHECK_VERSION: "三方一致（代码声明 / 清单登记 / 结构记录表）",
        _CHECK_TOPOLOGY: "拓扑一致（本次发布绑定当前拓扑版本）",
        _CHECK_STRUCTURE: "结构就绪（各域结构清单已执行完毕）",
        _CHECK_CONTRACT: "契约兼容（与上一发布版本对比）",
        _CHECK_VERSION_MONOTONIC: "清单版本（须大于当前最大值）",
    }
)


class ReleaseService(BaseFrameworkObject):
    """发布清单服务（校验 / 写入 / 回滚 / 查询）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        revisions: ReleaseRevisionPort | None = None,
        contract_breaches: ContractBreachReader | None = None,
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 平台库会话（写路径由调用方经工作单元提交）。
            revisions: 结构 revision 读面（跨库读，装配面 / 运维入口注入；只读查询可不传）。
            contract_breaches: 契约破坏性变更读面（缺省按声明版本主版本口径判定）。
            audit: 审计捕获器（可选；缺省不留痕）。
        """
        self._repo = ReleaseManifestRepository(session)
        self._domains = ReleaseManifestDomainRepository(session)
        self._topology = TenantTopologyRepository(session)
        self._revisions = revisions
        self._contract_breaches = contract_breaches
        self._audit = audit

    async def precheck(
        self,
        *,
        unit_key: str,
        tenant_scope: int = GLOBAL_TENANT_SCOPE,
        manifest_version: int | None = None,
        declared: Iterable[ReleaseDomainEntry] | None = None,
        topology_version: int | None = None,
        allow_breaking: bool = False,
    ) -> ReleasePrecheckResult:
        """执行 §3.3 的六条前置校验（只读，不改变任何状态）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围（`0` = 全局）。
            manifest_version: 本次批次号（缺省取当前最大值 + 1）。
            declared: 流水线声明的期望版本（缺省按服务目录登记值记录）。
            topology_version: 本次发布绑定的拓扑版本（缺省取当前版本）。
            allow_breaking: 是否放行契约破坏性变更（主版本升级流程用）。

        Returns:
            ReleasePrecheckResult: 逐项结论 + 将写入的明细。

        Raises:
            ParamError: 单元在拓扑中没有承载任何域（10001）。
        """
        rows = await self._topology.list_current(tenant_scope)
        fallback = False
        if not rows and tenant_scope != GLOBAL_TENANT_SCOPE:
            rows = await self._topology.list_current(GLOBAL_TENANT_SCOPE)
            fallback = tenant_scope != GLOBAL_TENANT_SCOPE and bool(rows)
        unit_domains = ConcurrentStableList(row.domain_key for row in rows if row.unit_key == unit_key)
        if not unit_domains:
            raise ParamError(f"部署单元 {unit_key} 在作用范围 {tenant_scope} 的拓扑中没有承载任何业务域")
        current_topology = max((row.topology_version for row in rows), default=0)
        target_topology = current_topology if topology_version is None else topology_version
        current_max = await self._repo.max_version(unit_key, tenant_scope)
        target_version = current_max + 1 if manifest_version is None else manifest_version
        declared_map = ConcurrentStableDict((entry.domain_key, entry) for entry in declared or ())
        entries = await self._entries(unit_domains, declared_map)
        items = ConcurrentStableList(
            (
                self._check_unit_complete(unit_domains, declared_map, fallback=fallback),
                self._check_versions(entries, declared_map),
                self._check_topology(target_topology, current_topology),
                self._check_structure(entries),
                await self._check_contract(unit_key, tenant_scope, entries, allow_breaking=allow_breaking),
                self._check_version(target_version, current_max),
            )
        )
        return ReleasePrecheckResult(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=target_version,
            topology_version=target_topology,
            entries=entries,
            items=items,
        )

    async def record(
        self,
        *,
        unit_key: str,
        tenant_scope: int = GLOBAL_TENANT_SCOPE,
        manifest_version: int | None = None,
        declared: Iterable[ReleaseDomainEntry] | None = None,
        topology_version: int | None = None,
        allow_breaking: bool = False,
        note: str = "",
        actor: int | None = None,
    ) -> ReleaseManifestSnapshot:
        """校验通过后写入发布清单（主表 + 明细，同一事务）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            manifest_version: 批次号（缺省取当前最大值 + 1）。
            declared: 流水线声明的期望版本。
            topology_version: 绑定的拓扑版本（缺省取当前版本）。
            allow_breaking: 是否放行契约破坏性变更。
            note: 发布摘要。
            actor: 发布人（自动化发布为空）。

        Returns:
            ReleaseManifestSnapshot: 落库后的发布快照。

        Raises:
            ConflictError: 前置校验未通过（10003，逐项列出原因）。
        """
        result = await self.precheck(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=manifest_version,
            declared=declared,
            topology_version=topology_version,
            allow_breaking=allow_breaking,
        )
        if not result.passed:
            raise ConflictError(self._failure_message(result))
        released_at = datetime.now(UTC)
        actor_id = actor if actor is not None else current_user_id.get()
        manifest = await self._repo.create_manifest(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=result.manifest_version,
            topology_version=result.topology_version,
            status=RELEASE_STATUS_RELEASED,
            released_at=released_at,
            released_by=actor_id,
            rolled_back_from=None,
            note=note or None,
        )
        await self._append_entries(manifest.id, result.entries, note=note)
        self._capture(
            manifest.id, unit_key=unit_key, version=result.manifest_version, count=len(result.entries), actor=actor_id
        )
        return ReleaseManifestSnapshot.from_models(manifest, await self._domain_entries(manifest.id))

    async def record_failure(
        self,
        *,
        unit_key: str,
        tenant_scope: int = GLOBAL_TENANT_SCOPE,
        topology_version: int = 0,
        note: str = "",
        actor: int | None = None,
    ) -> ReleaseManifestSnapshot:
        """记录一次执行阶段失败（只写主表行，不写明细；校验失败不走此路径）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            topology_version: 当时绑定的拓扑版本。
            note: 失败原因。
            actor: 操作人。

        Returns:
            ReleaseManifestSnapshot: 失败行快照（`domains` 为空）。
        """
        current_max = await self._repo.max_version(unit_key, tenant_scope)
        manifest = await self._repo.create_manifest(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=current_max + 1,
            topology_version=topology_version,
            status=RELEASE_STATUS_FAILED,
            released_at=datetime.now(UTC),
            released_by=actor if actor is not None else current_user_id.get(),
            rolled_back_from=None,
            note=note or "发布失败",
        )
        return ReleaseManifestSnapshot.from_models(manifest, ConcurrentStableList())

    async def plan_rollback(
        self,
        *,
        unit_key: str,
        tenant_scope: int = GLOBAL_TENANT_SCOPE,
        target_version: int | None = None,
        source_version: int | None = None,
    ) -> RollbackPlan:
        """生成批次回滚计划（不写库）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            target_version: 回退目标批次号（缺省取当前发布的上一成功发布）。
            source_version: 被回滚的批次号（缺省取最近一次成功发布）。

        Returns:
            RollbackPlan: 逐域回退步骤 + 阻断原因。

        Raises:
            ParamError: 回退目标批次不早于当前发布（10001）。
            NotFoundError: 没有可回滚的发布 / 目标发布（10002）。
        """
        source = await self._locate(unit_key, tenant_scope, version=source_version)
        if source is None:
            raise NotFoundError(f"部署单元 {unit_key}（范围 {tenant_scope}）没有可回滚的成功发布")
        target = await self._locate(unit_key, tenant_scope, version=target_version, before=source.manifest_version)
        if target is not None and target.manifest_version >= source.manifest_version:
            raise ParamError(
                f"回退目标批次必须早于当前发布：当前 {source.manifest_version}，目标 {target.manifest_version}"
            )
        if target is None:
            raise NotFoundError(
                f"部署单元 {unit_key}（范围 {tenant_scope}）在批次 {source.manifest_version} 之前没有成功发布，无法回滚"
            )
        current_entries = ConcurrentStableDict(
            (entry.domain_key, entry) for entry in await self._domain_entries(source.id)
        )
        target_entries = ConcurrentStableDict(
            (entry.domain_key, entry) for entry in await self._domain_entries(target.id)
        )
        steps = ConcurrentStableList(
            RollbackStep(
                domain_key=domain_key,
                from_revision=current_entries[domain_key].schema_revision,
                to_revision=target_entries[domain_key].schema_revision,
            )
            for domain_key in current_entries
            if domain_key in target_entries
        )
        blocked = ConcurrentStableList(
            f"域 {domain_key} 在目标发布（批次 {target.manifest_version}）中没有记录，无法逐域回退"
            for domain_key in current_entries
            if domain_key not in target_entries
        )
        return RollbackPlan(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            source=await self._snapshot(source),
            target=await self._snapshot(target),
            steps=steps,
            blocked_reasons=blocked,
        )

    async def rollback(
        self,
        *,
        unit_key: str,
        tenant_scope: int = GLOBAL_TENANT_SCOPE,
        target_version: int | None = None,
        confirmed: bool = False,
        note: str = "",
        actor: int | None = None,
    ) -> ReleaseManifestSnapshot:
        """按计划执行批次回滚（新增一行 `rolled_back`，不修改原行）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            target_version: 回退目标批次号（缺省取上一条成功发布）。
            confirmed: 是否已人工确认结构回退（涉及删列类回退必须显式确认）。
            note: 回滚原因。
            actor: 操作人。

        Returns:
            ReleaseManifestSnapshot: 回滚后的清单快照（状态 `rolled_back`）。

        Raises:
            ConflictError: 计划有阻断原因，或结构回退未确认（10003）。
        """
        plan = await self.plan_rollback(unit_key=unit_key, tenant_scope=tenant_scope, target_version=target_version)
        if not plan.executable:
            raise ConflictError("回滚计划被阻断：" + "；".join(plan.blocked_reasons))
        if plan.requires_confirmation and not confirmed:
            changed = ", ".join(step.domain_key for step in plan.steps if step.changes)
            raise ConflictError(f"回滚涉及结构变更（{changed}），需显式确认后执行（默认拒绝自动回退）")
        actor_id = actor if actor is not None else current_user_id.get()
        current_max = await self._repo.max_version(unit_key, tenant_scope)
        manifest = await self._repo.create_manifest(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=current_max + 1,
            topology_version=plan.target.topology_version,
            status=RELEASE_STATUS_ROLLED_BACK,
            released_at=datetime.now(UTC),
            released_by=actor_id,
            rolled_back_from=plan.source.id,
            note=note or f"回滚到批次 {plan.target.manifest_version}",
        )
        await self._append_entries(manifest.id, plan.target.domains, note=note, status=RELEASE_STATUS_ROLLED_BACK)
        self._capture(
            manifest.id,
            unit_key=unit_key,
            version=manifest.manifest_version,
            count=len(plan.target.domains),
            actor=actor_id,
        )
        return ReleaseManifestSnapshot.from_models(manifest, await self._domain_entries(manifest.id))

    async def recent(
        self, unit_key: str, tenant_scope: int = GLOBAL_TENANT_SCOPE, *, limit: int = 10
    ) -> ConcurrentStableList[ReleaseManifestSnapshot]:
        """取某单元最近的若干次发布（管理面查询：这个单元跑的是哪一版）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            limit: 条数上限。

        Returns:
            ConcurrentStableList[ReleaseManifestSnapshot]: 发布快照（批次号降序）。
        """
        return ConcurrentStableList(
            [await self._snapshot(row) for row in await self._repo.list_recent(unit_key, tenant_scope, limit=limit)]
        )

    async def get(self, manifest_id: int) -> ReleaseManifestSnapshot:
        """按主键取一次发布（含明细）。

        Args:
            manifest_id: 清单主键。

        Returns:
            ReleaseManifestSnapshot: 发布快照。

        Raises:
            NotFoundError: 清单不存在（10002）。
        """
        row = await self._repo.get(manifest_id)
        if row is None:
            raise NotFoundError(f"发布清单 {manifest_id} 不存在")
        return await self._snapshot(row)

    async def page(
        self,
        query: BasePageQuery,
        *,
        unit_key: str | None = None,
        tenant_scope: int | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[ReleaseManifestSnapshot], int]:
        """分页查询发布行（列表页不需要明细）。

        Args:
            query: 分页请求。
            unit_key: 部署单元筛选。
            tenant_scope: 作用范围筛选。
            status: 状态筛选。

        Returns:
            tuple[ConcurrentStableList[ReleaseManifestSnapshot], int]: (当前页快照, 总数)。
        """
        rows, total = await self._repo.page_rows(query, unit_key=unit_key, tenant_scope=tenant_scope, status=status)
        return ConcurrentStableList([await self._snapshot(row) for row in rows]), total

    async def _entries(
        self,
        unit_domains: ConcurrentStableList[str],
        declared_map: ConcurrentStableDict[str, ReleaseDomainEntry],
    ) -> ConcurrentStableList[ReleaseDomainEntry]:
        """按单元域集派生待写入明细（版本取服务目录登记值，revision 取记录表当前值）。

        声明值**不参与**派生：明细落盘的是「实际值」，声明值只在版本一致校验里与实际值比对——
        否则声明什么就记什么，校验形同虚设。

        Args:
            unit_domains: 单元承载的业务域（来自拓扑）。
            declared_map: 流水线声明的期望条目（可为空）。

        Returns:
            ConcurrentStableList[ReleaseDomainEntry]: 明细条目（按域升序）。
        """
        if self._revisions is None:
            raise ConfigError("发布校验需要结构 revision 读面（跨库读）：请经运维入口注入 ReleaseRevisionPort")
        services = self._service_map()
        domain_service = domain_service_view()
        entries: ConcurrentStableList[ReleaseDomainEntry] = ConcurrentStableList()
        for domain_key in sorted(unit_domains):
            service_key = domain_service.get(domain_key, "")
            record = services.get(service_key)
            declared = declared_map.get(domain_key)
            revision = await self._revisions.current(domain_key)
            entries.add(
                ReleaseDomainEntry(
                    domain_key=domain_key,
                    service_key=service_key,
                    service_version=record.service_version if record is not None else "",
                    contract_version=record.contract_version if record is not None else "",
                    schema_revision=revision,
                    note=declared.note if declared is not None else "",
                )
            )
        return entries

    @staticmethod
    def _service_map() -> ConcurrentStableDict[str, ModuleRecord]:
        """取服务目录视图（服务标识 → 登记记录）。

        Returns:
            ConcurrentStableDict[str, ModuleRecord]: 服务记录映射。
        """
        return ConcurrentStableDict(
            (record.service_key, record) for record in service_catalog_view() if record.service_key
        )

    def _check_unit_complete(
        self,
        unit_domains: ConcurrentStableList[str],
        declared_map: ConcurrentStableDict[str, ReleaseDomainEntry],
        *,
        fallback: bool,
    ) -> ReleaseCheckItem:
        """校验 1：单元所含域 = 拓扑记录中该单元全部域（不多不少）。

        Args:
            unit_domains: 拓扑给出的单元域集。
            declared_map: 流水线声明的域集。
            fallback: 是否借用了默认拓扑（租户尚无自身拓扑时）。

        Returns:
            ReleaseCheckItem: 结论。
        """
        note = "（租户无自身拓扑，按默认拓扑校验）" if fallback else ""
        if not declared_map:
            return ReleaseCheckItem(
                key=_CHECK_UNIT_COMPLETE,
                title=_TITLES[_CHECK_UNIT_COMPLETE],
                passed=True,
                detail=f"按拓扑派生 {len(unit_domains)} 个域{note}",
            )
        missing = ConcurrentStableList(domain for domain in unit_domains if domain not in declared_map)
        extra = ConcurrentStableList(domain for domain in declared_map if domain not in unit_domains)
        if missing or extra:
            parts = ConcurrentStableList[str]()
            if missing:
                parts.add(f"清单缺少域：{', '.join(missing)}")
            if extra:
                parts.add(f"清单多出域：{', '.join(extra)}")
            return ReleaseCheckItem(
                key=_CHECK_UNIT_COMPLETE,
                title=_TITLES[_CHECK_UNIT_COMPLETE],
                passed=False,
                detail="；".join(parts),
            )
        return ReleaseCheckItem(
            key=_CHECK_UNIT_COMPLETE,
            title=_TITLES[_CHECK_UNIT_COMPLETE],
            passed=True,
            detail=f"{len(unit_domains)} 个域与拓扑一致{note}",
        )

    @staticmethod
    def _check_versions(
        entries: ConcurrentStableList[ReleaseDomainEntry],
        declared_map: ConcurrentStableDict[str, ReleaseDomainEntry],
    ) -> ReleaseCheckItem:
        """校验 2：三方一致（声明值 / 登记值 / 结构记录表）。

        Args:
            entries: 按登记值与记录表派生出的明细。
            declared_map: 流水线声明的期望条目。

        Returns:
            ReleaseCheckItem: 结论（逐域列出差异）。
        """
        if not declared_map:
            return ReleaseCheckItem(
                key=_CHECK_VERSION,
                title=_TITLES[_CHECK_VERSION],
                passed=True,
                detail="未声明期望版本，按服务目录登记值与结构记录表落盘",
            )
        diffs = ConcurrentStableList[str]()
        for entry in entries:
            declared = declared_map.get(entry.domain_key)
            if declared is None:
                continue
            if declared.service_version and declared.service_version != entry.service_version:
                diffs.add(
                    f"{entry.domain_key}: 服务版本 声明 {declared.service_version} / 登记 {entry.service_version}"
                )
            if declared.contract_version and declared.contract_version != entry.contract_version:
                diffs.add(
                    f"{entry.domain_key}: 契约版本 声明 {declared.contract_version} / 登记 {entry.contract_version}"
                )
            if declared.schema_revision and declared.schema_revision != entry.schema_revision:
                diffs.add(
                    f"{entry.domain_key}: 结构 revision 声明 {declared.schema_revision}"
                    f" / 记录表 {entry.schema_revision}"
                )
        if diffs:
            return ReleaseCheckItem(
                key=_CHECK_VERSION,
                title=_TITLES[_CHECK_VERSION],
                passed=False,
                detail="；".join(diffs),
            )
        return ReleaseCheckItem(
            key=_CHECK_VERSION,
            title=_TITLES[_CHECK_VERSION],
            passed=True,
            detail=f"{len(declared_map)} 个域的声明值与登记值一致",
        )

    @staticmethod
    def _check_topology(target: int, current: int) -> ReleaseCheckItem:
        """校验 3：本次发布携带的拓扑版本 = 库中当前版本。

        Args:
            target: 本次发布绑定的拓扑版本。
            current: 库中当前拓扑版本。

        Returns:
            ReleaseCheckItem: 结论。
        """
        return ReleaseCheckItem(
            key=_CHECK_TOPOLOGY,
            title=_TITLES[_CHECK_TOPOLOGY],
            passed=target == current,
            detail=f"绑定 {target} / 当前 {current}",
        )

    @staticmethod
    def _check_structure(entries: ConcurrentStableList[ReleaseDomainEntry]) -> ReleaseCheckItem:
        """校验 4：各域结构清单已执行完毕（记录表已初始化）。

        待执行脚本是否为空由 `ops.migrate_tenants` 的版本单调校验把关（它才持有 alembic 脚本视图）；
        发布流程只校验「记录表已初始化」，避免在发布路径上再跑一遍脚本发现。

        Args:
            entries: 待写入明细。

        Returns:
            ReleaseCheckItem: 结论。
        """
        missing = ConcurrentStableList(
            entry.domain_key
            for entry in entries
            if entry.schema_revision is None and any(series.tables for series in domain_series(entry.domain_key))
        )
        if missing:
            return ReleaseCheckItem(
                key=_CHECK_STRUCTURE,
                title=_TITLES[_CHECK_STRUCTURE],
                passed=False,
                detail=f"以下域的结构记录表尚未初始化（请先执行清单）：{', '.join(missing)}",
            )
        return ReleaseCheckItem(
            key=_CHECK_STRUCTURE,
            title=_TITLES[_CHECK_STRUCTURE],
            passed=True,
            detail=f"{len(entries)} 个域的结构记录表均已初始化",
        )

    async def _check_contract(
        self,
        unit_key: str,
        tenant_scope: int,
        entries: ConcurrentStableList[ReleaseDomainEntry],
        *,
        allow_breaking: bool,
    ) -> ReleaseCheckItem:
        """校验 5：与上一发布版本对比契约兼容性。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            entries: 本次明细。
            allow_breaking: 是否放行破坏性变更。

        Returns:
            ReleaseCheckItem: 结论。
        """
        previous = await self._repo.latest(unit_key, tenant_scope)
        if previous is None:
            return ReleaseCheckItem(
                key=_CHECK_CONTRACT,
                title=_TITLES[_CHECK_CONTRACT],
                passed=True,
                detail="首次发布，无历史基线可供对比",
            )
        previous_entries = ConcurrentStableDict(
            (entry.domain_key, entry) for entry in await self._domain_entries(previous.id)
        )
        problems = ConcurrentStableList[str]()
        for entry in entries:
            before = previous_entries.get(entry.domain_key)
            if before is None:
                continue
            if self._contract_breaches is not None:
                breaches = await self._contract_breaches(entry.service_key)
                if breaches:
                    problems.add(f"{entry.domain_key}: {', '.join(breaches)}")
                continue
            if _major(before.contract_version) != _major(entry.contract_version):
                problems.add(f"{entry.domain_key}: 契约主版本 {before.contract_version} → {entry.contract_version}")
        if problems and not allow_breaking:
            return ReleaseCheckItem(
                key=_CHECK_CONTRACT,
                title=_TITLES[_CHECK_CONTRACT],
                passed=False,
                detail="；".join(problems) + "（确需破坏性变更请走主版本升级流程并显式放行）",
            )
        if problems:
            return ReleaseCheckItem(
                key=_CHECK_CONTRACT,
                title=_TITLES[_CHECK_CONTRACT],
                passed=True,
                detail="已显式放行：" + "；".join(problems),
            )
        return ReleaseCheckItem(
            key=_CHECK_CONTRACT,
            title=_TITLES[_CHECK_CONTRACT],
            passed=True,
            detail=f"与批次 {previous.manifest_version} 对比无破坏性变更",
        )

    @staticmethod
    def _check_version(target: int, current_max: int) -> ReleaseCheckItem:
        """校验 6：批次号增长（不允许回退或重复）。

        Args:
            target: 本次批次号。
            current_max: 当前最大批次号。

        Returns:
            ReleaseCheckItem: 结论。
        """
        return ReleaseCheckItem(
            key=_CHECK_VERSION_MONOTONIC,
            title=_TITLES[_CHECK_VERSION_MONOTONIC],
            passed=target > current_max,
            detail=f"本次 {target} / 当前最大 {current_max}",
        )

    async def _locate(
        self,
        unit_key: str,
        tenant_scope: int,
        *,
        version: int | None,
        before: int | None = None,
    ) -> SysReleaseManifest | None:
        """定位某次成功发布（按批次号，或缺省取最近一次）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            version: 指定批次号；None 取最近一次。
            before: 只看批次号小于该值的行。

        Returns:
            SysReleaseManifest | None: 发布行；没有返回 None。
        """
        if version is None:
            return await self._repo.latest(unit_key, tenant_scope, before_version=before)
        row = await self._repo.find_version(unit_key, tenant_scope, version)
        if row is None or row.status not in RELEASE_STATUSES or row.status == RELEASE_STATUS_FAILED:
            return None
        return row

    async def _snapshot(self, row: SysReleaseManifest) -> ReleaseManifestSnapshot:
        """由主表行构造含明细的快照。

        Args:
            row: 主表行。

        Returns:
            ReleaseManifestSnapshot: 发布快照。
        """
        return ReleaseManifestSnapshot.from_models(row, await self._domain_entries(row.id))

    async def _domain_entries(self, manifest_id: int) -> ConcurrentStableList[ReleaseDomainEntry]:
        """取某次发布的明细条目（按域升序）。

        Args:
            manifest_id: 清单主键。

        Returns:
            ConcurrentStableList[ReleaseDomainEntry]: 明细条目。
        """
        return ConcurrentStableList(
            ReleaseDomainEntry.from_model(row) for row in await self._domains.list_by_manifest(manifest_id)
        )

    async def _append_entries(
        self,
        manifest_id: int,
        entries: ConcurrentStableList[ReleaseDomainEntry],
        *,
        note: str,
        status: str = RELEASE_STATUS_RELEASED,
    ) -> None:
        """写入明细行（主表落库后调用，同事务）。

        Args:
            manifest_id: 清单主键。
            entries: 明细条目。
            note: 明细说明（发布摘要）。
            status: 明细状态。
        """
        rows = ConcurrentStableList(
            SysReleaseManifestDomain(
                manifest_id=manifest_id,
                domain_key=entry.domain_key,
                schema_revision=entry.schema_revision,
                service_version=entry.service_version,
                contract_version=entry.contract_version,
                status=status,
                note=note or None,
            )
            for entry in entries
        )
        await self._domains.append_entries(manifest_id, rows)

    @staticmethod
    def _failure_message(result: ReleasePrecheckResult) -> str:
        """把未通过的校验项拼为一条可读的拒绝原因。

        Args:
            result: 预检结论。

        Returns:
            str: 拒绝原因（逐项「名称：详情」）。
        """
        details = ConcurrentStableList(f"{item.title}——{item.detail}" for item in result.failures())
        return "发布被拒绝：" + "；".join(details)

    def _capture(self, manifest_id: int, *, unit_key: str, version: int, count: int, actor: int | None) -> None:
        """写审计留痕（发布 / 回滚各一条，不逐域记）。

        Args:
            manifest_id: 清单主键。
            unit_key: 部署单元标识。
            version: 批次号。
            count: 域数。
            actor: 操作人。
        """
        if self._audit is None:
            return
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
            (
                FieldChange(field="unit_key", old=None, new=unit_key),
                FieldChange(field="manifest_version", old=None, new=version),
                FieldChange(field="domains", old=None, new=count),
            )
        )
        self._audit.capture(table=_TABLE, model_id=manifest_id, changes=changes, actor=actor)


def _major(version: str) -> str:
    """取契约版本的主版本段（无版本信息时原样返回）。

    Args:
        version: 版本串（如 `0.1.0`）。

    Returns:
        str: 主版本段（如 `0`）；空串返回空串。
    """
    if not version:
        return ""
    return version.split(".", 1)[0]
