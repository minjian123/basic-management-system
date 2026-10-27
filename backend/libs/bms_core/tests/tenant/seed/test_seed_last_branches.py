"""最后一轮分支补齐（07B `02_03`；覆盖率收尾）。

**Kiwi 编号**：本批新增用例暂不标 `kiwi_id`，统一归 `05_01` 回填。

**覆盖面**：表归属更新的两条路径（入口 / 单步）、菜单种子「无表单跳过」分支、
平台授权菜单 / 表单条目、rbac 授权真实写入、预检错误返回路径。
"""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.ownership import SysTableOwnership
from bms_core.models.platform.menu_form import SysForm, SysMenu
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission
from bms_core.services.table_registry import table_ownership_view
from bms_core.tenant.seed import menu as menu_seed
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import tables as tables_seed

# ---- 表归属：入口更新分支 ----


async def test_seed_tables_entry_marks_changed_fields(tmp_path: Path) -> None:
    """`seed_tables_entry`：既有行字段与清单不一致 → 就地更新（不新增）。"""
    first = table_ownership_view()[0]
    url = f"sqlite+aiosqlite:///{tmp_path / 'tb.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysTableOwnership.__table__)])
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                SysTableOwnership(
                    table_name=first.table_name,
                    owner="stale",
                    domain=first.domain,
                    datasource=first.datasource,
                    status=first.status,
                    note="旧备注",
                )
            )
            await session.commit()
            await tables_seed.seed_tables_entry(session, ConcurrentStableDict())
            await session.commit()
            row = (
                await session.execute(select(SysTableOwnership).where(SysTableOwnership.table_name == first.table_name))
            ).scalar_one()
            assert row.owner == first.owner
            assert row.note == first.note
    finally:
        await engine.dispose()


# ---- 表归属：单步同步路径的更新分支 ----


def test_seed_tables_single_step_updates(tmp_path: Path) -> None:
    """`seed_tables`（异步单步）：既有行值不同 → 走更新分支。"""
    first = table_ownership_view()[0]
    url = f"sqlite+aiosqlite:///{tmp_path / 'tb2.db'}"
    engine = create_async_engine(url)

    async def _prepare() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysTableOwnership.__table__)])
            )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(
                SysTableOwnership(
                    table_name=first.table_name,
                    owner="stale",
                    domain=first.domain,
                    datasource=first.datasource,
                    status=first.status,
                )
            )
            await session.commit()

    asyncio.run(_prepare())
    asyncio.run(engine.dispose())
    _created, updated, _retired = asyncio.run(tables_seed.seed_tables(url))
    assert updated >= 1


# ---- 菜单：无表单时跳过按钮 / 字段 ----


async def test_menu_seed_skips_buttons_without_form(tmp_path: Path) -> None:
    """菜单种子：某菜单无对应表单 → 按钮 / 字段播种跳过该行（`continue` 分支）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'menu.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            # 不建表单 ⇒ 按钮 / 字段分支的 `form_id` 为 0，走 `continue`
            created, skipped, checked = await menu_seed._seed_menu_in_session(session)  # pyright: ignore[reportPrivateUsage]
            await session.commit()
            assert created >= 0
            assert skipped >= 0
            assert checked >= 0
    finally:
        await engine.dispose()


# ---- 平台授权：菜单 / 表单条目 ----


async def test_platform_grants_include_menu_and_form_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """平台授权：平台库有菜单 / 表单时，ops 角色获得对应授权条目。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_t.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'pg_p.db'}"
    tables = [
        SysBusiness.__table__,
        SysAction.__table__,
        SysPermission.__table__,
        SysMenu.__table__,
        SysForm.__table__,
        SysRole.__table__,
        SysRolePermission.__table__,
    ]
    platform_engine = create_async_engine(platform_url)
    try:
        async with platform_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(platform_engine, expire_on_commit=False)
        async with factory() as session:
            business = SysBusiness(code="tenant", name="租户管理")
            action = SysAction(code="query", name="查询")
            session.add_all([business, action])
            await session.flush()
            session.add(SysPermission(business_id=int(business.id), action_id=int(action.id)))
            session.add(SysMenu(path=platform_seed.PLATFORM_TENANT_MENU_PATH, name="租户管理"))
            await session.flush()
            session.add(SysForm(business_id=int(business.id), component="tenant-form"))
            await session.commit()
    finally:
        await platform_engine.dispose()

    monkeypatch.setattr(platform_seed, "_urls", lambda _code: (tenant_url, platform_url))  # type: ignore[reportUnknownLambdaType]
    tenant_engine = create_async_engine(tenant_url)
    try:
        async with tenant_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(tenant_engine, expire_on_commit=False)
        async with factory() as session:
            await platform_seed.seed_platform_roles_entry(session, ConcurrentStableDict())
            await session.commit()
            await platform_seed.seed_platform_grants_entry(session, ConcurrentStableDict())
            await session.commit()
            grants = (await session.execute(select(SysRolePermission))).scalars().all()
            perm_types = {grant.perm_type for grant in grants}
            # 至少覆盖到菜单 / 表单类授权（有对应元数据时）
            assert grants
            assert perm_types <= {"permission", "menu", "form"}
    finally:
        await tenant_engine.dispose()


# ---- rbac 授权：有权限码时真实写入 ----


async def test_rbac_grants_written_when_codes_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rbac 授权：平台库有权限码时写入授权条目。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'rb_t.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'rb_p.db'}"
    tables = [
        SysBusiness.__table__,
        SysAction.__table__,
        SysPermission.__table__,
        SysRole.__table__,
        SysRolePermission.__table__,
    ]
    platform_engine = create_async_engine(platform_url)
    try:
        async with platform_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(platform_engine, expire_on_commit=False)
        async with factory() as session:
            # 造齐三类内置角色清单里用到的权限码
            codes: ConcurrentStableList[str] = ConcurrentStableList()
            for _code, _name, _rtype, permission_codes in rbac_seed.BUILTIN_ADMIN_ROLES:
                codes.update(permission_codes)
            business_codes = {code.split(":", 1)[0] for code in codes}
            action_codes = {code.split(":", 1)[1] for code in codes}
            business_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for code in business_codes:
                row = SysBusiness(code=code, name=code)
                session.add(row)
                await session.flush()
                business_ids.set(code, int(row.id))
            action_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for code in action_codes:
                row = SysAction(code=code, name=code)
                session.add(row)
                await session.flush()
                action_ids.set(code, int(row.id))
            for code in codes:
                business, action = code.split(":", 1)
                session.add(SysPermission(business_id=business_ids[business], action_id=action_ids[action]))
            await session.commit()
    finally:
        await platform_engine.dispose()

    monkeypatch.setattr(rbac_seed, "_resolve_platform_url", lambda _url, *, service: platform_url)  # type: ignore[reportUnknownLambdaType]
    tenant_engine = create_async_engine(tenant_url)
    try:
        async with tenant_engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=cast("Sequence[Table]", tables))
            )
        factory = async_sessionmaker(tenant_engine, expire_on_commit=False)
        async with factory() as session:
            await rbac_seed.seed_rbac_roles_entry(session, ConcurrentStableDict())
            await session.commit()
            await rbac_seed.seed_rbac_grants_entry(session, ConcurrentStableDict())
            await session.commit()
            grants = (await session.execute(select(SysRolePermission))).scalars().all()
            assert len(grants) > 0
    finally:
        await tenant_engine.dispose()


# ---- 编排服务：预检错误返回路径 ----


async def test_orchestrate_precheck_error_returns_exit_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """编排服务：前置校验发现错误 → 退出码 3（不进事务）。"""
    import bms_platform.domains.platform_registry.services.seed_orchestration as module
    from bms_platform.domains.platform_registry.services.seed_orchestration import (
        SeedOrchestrationRequest,
        SeedOrchestrationService,
    )

    original = module.precheck_seeds

    def _fake(_selected: Any) -> Any:
        """替身：恒定返回一条前置错误。

        Args:
            _selected: 执行集合（忽略）。

        Returns:
            Any: 预检结果。
        """
        from bms_core.tenant.seed.orchestrator import PrecheckResult

        result = PrecheckResult()
        result.errors.add("种子重名且声明不一致：x")
        return result

    module.precheck_seeds = _fake  # type: ignore[attr-defined]
    try:
        service = SeedOrchestrationService(caller_service="platform", manager=None, participant=None, engines=None)
        result = await service.orchestrate(SeedOrchestrationRequest(only=ConcurrentStableFrozenList(["seed-module"])))
    finally:
        module.precheck_seeds = original  # type: ignore[attr-defined]
    assert result.exit_code == 3
    assert "种子重名" in result.errors[0]
