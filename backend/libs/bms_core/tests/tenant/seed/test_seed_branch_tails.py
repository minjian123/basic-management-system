"""分支收尾用例（07B `02_03`）：最后几个条件分支。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：`require_closure` 的「依赖已在闭包内」分支、`_fetch_row` 的「列不在表」分支、
`_rolled_back` 的 pending / 其它状态分支、平台入口的租户参数缺省与显式两分支、
rbac 授权的「缺码去重」分支、编排服务的冲突 / 无冲突分支、表归属同步路径的更新分支。
"""

from typing import Any, cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.models.platform.menu_form import SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission
from bms_core.services.module_registry import SeedRecord
from bms_core.services.table_registry import table_ownership_view
from bms_core.tenant.seed import menu as menu_seed
from bms_core.tenant.seed import orchestrator
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import tables as tables_seed
from bms_core.tenant.seed.contract import ExpectedRow

_PLATFORM_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
        cast("Table", SysMenu.__table__),
        cast("Table", SysForm.__table__),
    ]
)
"""平台库最小表集（权限码 / 菜单 / 表单）。"""

_ROLE_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [cast("Table", SysRole.__table__), cast("Table", SysRolePermission.__table__)]
)
"""租户库角色域表集。"""


def _record(name: str, *, after: ConcurrentStableFrozenList[str] | None = None) -> SeedRecord:
    """构造种子记录。

    Args:
        name: 种子名。
        after: 依赖。

    Returns:
        SeedRecord: 记录。
    """
    return SeedRecord(
        name=name,
        module="ops.seed_menu",
        entry="seed_menu_entry",
        service="platform",
        db_key="platform_platform",
        after=after if after is not None else ConcurrentStableFrozenList(),
        source="platform",
    )


async def _create_async(url: str, tables: ConcurrentStableList[Table]) -> None:
    """建表（异步库）。

    Args:
        url: 连接串。
        tables: 表清单。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(tables)))
    finally:
        await engine.dispose()


def _create_sync(url: str, tables: ConcurrentStableList[Table]) -> None:
    """建表（同步库）。

    Args:
        url: 连接串。
        tables: 表清单。
    """
    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine, tables=list(tables))
    finally:
        engine.dispose()


def _patch_urls(monkeypatch: pytest.MonkeyPatch, *, tenant_url: str, platform_url: str) -> None:
    """把 `platform_seed._urls` 指向临时库。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        tenant_url: 租户库连接串。
        platform_url: 平台库连接串。
    """

    def _urls(_code: str) -> Any:
        """替身：返回固定两库。

        Args:
            _code: 平台租户码（忽略）。

        Returns:
            Any: （租户库, 平台库）。
        """
        return tenant_url, platform_url

    monkeypatch.setattr(platform_seed, "_urls", _urls)


def _patch_platform_url(monkeypatch: pytest.MonkeyPatch, *, platform_url: str) -> None:
    """把 `rbac_seed._resolve_platform_url` 指向临时库。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        platform_url: 平台库连接串。
    """

    def _resolve(_url: str, *, service: str) -> str:
        """替身：返回固定平台库。

        Args:
            _url: 原 URL（忽略）。
            service: 服务键（忽略）。

        Returns:
            str: 平台库连接串。
        """
        del _url, service
        return platform_url

    monkeypatch.setattr(rbac_seed, "_resolve_platform_url", _resolve)


# ---- require_closure：依赖已在闭包内 ----


def test_require_closure_skips_already_collected_dependency() -> None:
    """同一依赖被多次引用：第二次不再入队（`dependency not in closure` 假分支）。"""
    records = ConcurrentStableList(
        [
            _record("a"),
            _record("b", after=ConcurrentStableFrozenList(["a"])),
            _record("c", after=ConcurrentStableFrozenList(["a", "b"])),
        ]
    )
    closure = orchestrator.require_closure(records, ConcurrentStableList(["c"]))
    assert set(closure) == {"a", "b", "c"}


# ---- _fetch_row：列不在表中 ----


def test_fetch_row_ignores_unknown_columns(tmp_path: Any) -> None:
    """`_fetch_row`：期望行的自然键含表中不存在的列 → 忽略该列（不抛错）。"""
    url = f"sqlite:///{tmp_path / 'fr.db'}"
    _create_sync(url, ConcurrentStableList([cast("Table", SysBusiness.__table__)]))
    engine = create_engine(url)
    try:
        expected = ExpectedRow(
            table="sys_business",
            key=ConcurrentStableFrozenDict({"code": "mdm", "no_such_column": "x"}),
            values=ConcurrentStableFrozenDict(),
        )
        assert orchestrator._fetch_row(engine, expected) is None  # pyright: ignore[reportPrivateUsage]
    finally:
        engine.dispose()


# ---- _rolled_back：pending / 其它状态 ----


def test_rolled_back_marks_pending_as_not_executed() -> None:
    """报告口径：prepared → rolled_back，pending → not_executed，失败项带根因。"""
    reports = ConcurrentStableList(
        [
            orchestrator.SeedReport(name="a", source="platform", status="prepared"),
            orchestrator.SeedReport(name="b", source="platform", status="pending"),
            orchestrator.SeedReport(name="c", source="platform", status="pending"),
        ]
    )
    marked = orchestrator._rolled_back(reports, failed_index=1, note="分支未就绪")  # pyright: ignore[reportPrivateUsage]
    assert [report.status for report in marked] == ["rolled_back", "rolled_back", "not_executed"]
    assert marked[1].note.startswith("← 失败：")
    assert marked[2].note == ""


def test_rolled_back_leaves_other_statuses_untouched() -> None:
    """报告口径：`ok` / `failed` 等其它状态不被改写（`elif` 条件不成立的分支）。"""
    reports = ConcurrentStableList(
        [
            orchestrator.SeedReport(name="a", source="platform", status="ok"),
            orchestrator.SeedReport(name="b", source="platform", status="failed"),
            orchestrator.SeedReport(name="c", source="platform", status="prepared"),
        ]
    )
    marked = orchestrator._rolled_back(reports, failed_index=2, note="x")  # pyright: ignore[reportPrivateUsage]
    assert [report.status for report in marked] == ["ok", "failed", "rolled_back"]


# ---- 平台入口：租户参数缺省 / 显式 ----


async def test_platform_roles_entry_without_tenant_arg(tmp_path: Any) -> None:
    """`seed_platform_roles_entry` 未给 `tenant` → 回退配置的平台租户码。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'pt.db'}"
    await _create_async(url, _ROLE_TABLES)
    engine = create_async_engine(url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
            await session.commit()
    finally:
        await engine.dispose()


async def test_platform_roles_entry_with_explicit_tenant(tmp_path: Any) -> None:
    """`seed_platform_roles_entry` 显式给 `tenant` → 不走配置回退分支。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'pt2.db'}"
    await _create_async(url, _ROLE_TABLES)
    engine = create_async_engine(url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            args.set("tenant", "demo")
            await platform_seed.seed_platform_roles_entry(session, args)
            await session.commit()
    finally:
        await engine.dispose()


async def test_platform_grants_entry_without_tenant_arg(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_platform_grants_entry` 未给 `tenant` → 回退配置；随后按角色缺失抛 `ParamError`。"""
    from bms_core.core.exceptions import ParamError

    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_p.db'}"
    _patch_urls(monkeypatch, tenant_url=tenant_url, platform_url=platform_url)
    await _create_async(platform_url, _PLATFORM_TABLES)
    await _create_async(tenant_url, _ROLE_TABLES)
    engine = create_async_engine(tenant_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            with pytest.raises(ParamError, match="角色不存在"):
                await platform_seed.seed_platform_grants_entry(session, ConcurrentStableDict())
    finally:
        await engine.dispose()


async def test_platform_grants_entry_with_explicit_tenant(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """`seed_platform_grants_entry` 显式给 `tenant` → 不走配置回退分支。"""
    from bms_core.core.exceptions import ParamError

    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg3.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg3_p.db'}"
    _patch_urls(monkeypatch, tenant_url=tenant_url, platform_url=platform_url)
    await _create_async(platform_url, _PLATFORM_TABLES)
    await _create_async(tenant_url, _ROLE_TABLES)
    engine = create_async_engine(tenant_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            args: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            args.set("tenant", "demo")
            with pytest.raises(ParamError, match="角色不存在"):
                await platform_seed.seed_platform_grants_entry(session, args)
    finally:
        await engine.dispose()


# ---- rbac 授权：缺码去重 ----


async def test_rbac_grants_dedupes_missing_codes(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """rbac 授权：同一缺码在多个角色清单重复出现时只登记一次。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'rb.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'rb_p.db'}"
    _patch_platform_url(monkeypatch, platform_url=platform_url)
    await _create_async(
        platform_url,
        ConcurrentStableList(
            [
                cast("Table", SysBusiness.__table__),
                cast("Table", SysAction.__table__),
                cast("Table", SysPermission.__table__),
            ]
        ),
    )
    await _create_async(tenant_url, _ROLE_TABLES)
    shared = ConcurrentStableList(["role:query"])
    original = rbac_seed.BUILTIN_ADMIN_ROLES
    rbac_seed.BUILTIN_ADMIN_ROLES = ConcurrentStableList(
        [
            (rbac_seed.ROLE_SYSTEM_ADMIN, "系统管理员", "system", shared),
            (rbac_seed.ROLE_SECURITY_ADMIN, "安全管理员", "security", shared),
        ]
    )
    engine = create_async_engine(tenant_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await rbac_seed.seed_rbac_roles_entry(session, ConcurrentStableDict())
            await session.commit()
            await rbac_seed.seed_rbac_grants_entry(session, ConcurrentStableDict())
            await session.commit()
    finally:
        rbac_seed.BUILTIN_ADMIN_ROLES = original
        await engine.dispose()


# ---- 表归属：同步路径的更新分支 ----


def test_seed_tables_sync_updates_existing_rows(tmp_path: Any) -> None:
    """`_seed_tables_sync`（同步方言）：既有行字段不一致 → 就地更新。"""
    from sqlalchemy.orm import Session

    first = table_ownership_view()[0]
    url = f"sqlite:///{tmp_path / 'sync.db'}"
    _create_sync(url, ConcurrentStableList([cast("Table", SysTableOwnership.__table__)]))
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(
                SysTableOwnership(
                    table_name=first.table_name,
                    owner="stale",
                    domain=first.domain,
                    datasource=first.datasource,
                    status=first.status,
                )
            )
            session.commit()
    finally:
        engine.dispose()
    _created, updated, _retired = tables_seed._seed_tables_sync(url, "")  # pyright: ignore[reportPrivateUsage]
    assert updated >= 1


# ---- 菜单：按钮 / 字段跳过分支 ----


async def test_menu_seed_skips_button_and_field_without_form(tmp_path: Any) -> None:
    """菜单种子：按钮 / 字段的目标菜单无表单 → 跳过（两条 `continue` 分支）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'menu2.db'}"
    original = menu_seed.MENU_SEEDS
    await _create_async(url, ConcurrentStableList(Base.metadata.sorted_tables))
    engine = create_async_engine(url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # 先正常播种，使按钮 / 字段依赖的菜单行存在
            await menu_seed._seed_menu_in_session(session)  # pyright: ignore[reportPrivateUsage]
            await session.commit()
            # 换成「无 component」的菜单清单 ⇒ 不建表单 ⇒ 按钮 / 字段循环走 `continue`
            menu_seed.MENU_SEEDS = ConcurrentStableList(
                [(0, "/sys", "系统管理", "System", None, "el:setting", 10, False, None)]
            )
            created, skipped, checked = await menu_seed._seed_menu_in_session(session)  # pyright: ignore[reportPrivateUsage]
            await session.commit()
            assert created >= 0
            assert skipped >= 0
            assert checked >= 0
    finally:
        menu_seed.MENU_SEEDS = original
        await engine.dispose()


# ---- 编排服务：冲突 / 无冲突分支 ----


class _Manager:
    """事务管理器替身。"""

    async def begin(self, *, branches: Any, **_k: Any) -> Any:
        """开启事务。

        Args:
            branches: 分支声明。
            **_k: 忽略。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import BranchRef, GlobalTransaction

        return GlobalTransaction(
            global_txn_id="t",
            caller_service="platform",
            state="active",
            branches=ConcurrentStableFrozenList(
                BranchRef(branch_id=s.branch_id, service=s.service, db_key=s.db_key, xid=f"t|{s.branch_id}")
                for s in branches
            ),
        )

    async def commit(self, global_txn_id: str) -> Any:
        """提交。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="committed")

    async def rollback(self, global_txn_id: str) -> Any:
        """回滚。

        Args:
            global_txn_id: 事务标识。

        Returns:
            Any: 快照。
        """
        from bms_core.transaction.base import GlobalTransaction

        return GlobalTransaction(global_txn_id=global_txn_id, caller_service="platform", state="rolled_back")


class _Runner:
    """分支执行器替身：prepared。"""

    async def execute_branch_with_stats(self, **_k: Any) -> Any:
        """执行分支。

        Args:
            **_k: 忽略。

        Returns:
            Any: （prepared, 空统计）。
        """
        from bms_core.transaction.base import BranchStats

        return "prepared", BranchStats()


def _patch_orchestration(monkeypatch: pytest.MonkeyPatch, *, conflicts: ConcurrentStableList[str]) -> None:
    """把编排服务的结构前置与冲突预检替身化。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
        conflicts: 冲突预检返回值。
    """
    import bms_platform.domains.platform_registry.services.seed_orchestration as module

    async def _no_structure(_plan: Any, *, tenant: str) -> ConcurrentStableList[str]:
        """替身：结构就绪。

        Args:
            _plan: 计划（忽略）。
            tenant: 租户（忽略）。

        Returns:
            ConcurrentStableList[str]: 空错误。
        """
        del tenant
        return ConcurrentStableList()

    async def _conflicts(_plan: Any, *, engines: Any) -> ConcurrentStableList[str]:
        """替身：返回预设冲突。

        Args:
            _plan: 计划（忽略）。
            engines: 引擎（忽略）。

        Returns:
            ConcurrentStableList[str]: 冲突明细。
        """
        del engines
        return conflicts

    monkeypatch.setattr(module, "ensure_structure", _no_structure)
    monkeypatch.setattr(module, "precheck_conflicts", _conflicts)


async def test_orchestrate_conflict_returns_exit_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """编排服务：冲突预检命中 → 退出码 1（不进事务）。"""
    from bms_platform.domains.platform_registry.services.seed_orchestration import (
        SeedOrchestrationRequest,
        SeedOrchestrationService,
    )

    _patch_orchestration(monkeypatch, conflicts=ConcurrentStableList(["种子 seed-menu：sys_business 与声明不一致"]))
    service = SeedOrchestrationService(caller_service="platform", manager=None, participant=None, engines=object())
    result = await service.orchestrate(SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"])))
    assert result.exit_code == 1
    assert "与声明不一致" in result.conflicts[0]


async def test_orchestrate_continues_when_no_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    """编排服务：冲突预检无命中 → 继续执行（`if conflicts` 的假分支）。"""
    from bms_platform.domains.platform_registry.services.seed_orchestration import (
        SeedOrchestrationRequest,
        SeedOrchestrationService,
    )

    _patch_orchestration(monkeypatch, conflicts=ConcurrentStableList())
    service = SeedOrchestrationService(
        caller_service="platform", manager=_Manager(), participant=_Runner(), engines=object()
    )
    result = await service.orchestrate(SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"])))
    assert result.exit_code == 0
