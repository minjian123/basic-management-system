"""平台租户 RBAC 种子用例（Kiwi 2343）：`bms_core/tenant/seed/platform.py`。

覆盖：两角色 / 授权 / 绑定幂等、`assign_user` 命中与未命中、`--dry-run` 不建连、CLI 退出码与输出。
"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.platform.menu import SysAction, SysBusiness, SysForm, SysMenu, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.tenant.seed import platform as platform_seed

_BUSINESSES = ("sys", "tenant", "menu", "business", "action", "permission", "user-extension")
_ACTIONS = ("query", "manage", "create", "update", "delete", "generate")


@pytest_asyncio.fixture
async def urls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[str, str]]:
    """建租户库与平台库，播种平台业务 / 动作码 / 菜单 / 表单（供种子授权）。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        tuple[str, str]: （租户库 URL，平台库 URL）。
    """
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'platform_platform.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    tenant_engine = create_async_engine(tenant_url)
    tenant_tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysUser.__table__),
    ]
    async with tenant_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tenant_tables))
    await tenant_engine.dispose()
    platform_engine = create_async_engine(platform_url)
    platform_tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
        cast("Table", SysMenu.__table__),
        cast("Table", SysForm.__table__),
    ]
    async with platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    async with factory() as session:
        business_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for code in _BUSINESSES:
            row = SysBusiness(code=code, name=code)
            session.add(row)
            await session.flush()
            business_ids.set(code, int(row.id))
        action_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for code in _ACTIONS:
            row = SysAction(code=code, name=code)
            session.add(row)
            await session.flush()
            action_ids.set(code, int(row.id))
        for business in _BUSINESSES:
            for action in _ACTIONS:
                session.add(SysPermission(business_id=business_ids[business], action_id=action_ids[action]))
        session.add(SysMenu(path="/platform", name="平台"))
        session.add(SysMenu(path="/platform/tenants", name="租户管理"))
        await session.flush()
        session.add(SysForm(business_id=business_ids["tenant"], component="tenant-form"))
        await session.commit()
    await platform_engine.dispose()
    monkeypatch.setenv(
        "BMS_DATABASE__TENANTS__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/{{service}}_{{tenant}}.db"
    )
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", f"sqlite+aiosqlite:///{tmp_path}/{{service}}.db")
    from bms_core.core.config import get_settings

    get_settings.cache_clear()
    yield tenant_url, platform_url
    get_settings.cache_clear()


async def _counts(tenant_url: str) -> tuple[int, int, int]:
    """读角色 / 授权 / 绑定行数。

    Args:
        tenant_url: 租户库连接串。

    Returns:
        tuple[int, int, int]: （角色数，授权数，绑定数）。
    """
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            roles = (await session.execute(select(SysRole))).scalars().all()
            grants = (await session.execute(select(SysRolePermission))).scalars().all()
            bindings = (await session.execute(select(SysUserRole))).scalars().all()
            return len(roles), len(grants), len(bindings)
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2343)
async def test_seed_platform_creates_roles_and_grants_idempotently(urls: tuple[str, str]) -> None:
    """首次播种建两角色与授权；重复执行全跳过（幂等）。"""
    tenant_url, _ = urls
    first = await platform_seed.seed_platform_rbac(platform_code="platform")
    assert first.roles_created == 2
    assert first.grants_created > 0
    assert first.assignments_created == 0
    roles, grants, _ = await _counts(tenant_url)
    assert roles == 2
    assert grants == first.grants_created

    second = await platform_seed.seed_platform_rbac(platform_code="platform")
    assert second.roles_created == 0
    assert second.grants_created == 0
    assert second.roles_skipped == 2
    assert second.grants_skipped == first.grants_created
    roles_after, grants_after, _ = await _counts(tenant_url)
    assert (roles_after, grants_after) == (roles, grants)


@pytest.mark.kiwi_id(2343)
async def test_seed_platform_assigns_existing_user_only(urls: tuple[str, str]) -> None:
    """`assign_user` 命中账号才绑定；未命中不绑定（幂等：重复绑定记跳过）。"""
    tenant_url, _ = urls
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            session.add(SysUser(username="admin", password_hash="x", name="管理员"))
            await session.commit()
    finally:
        await engine.dispose()

    bound = await platform_seed.seed_platform_rbac(platform_code="platform", assign_user="admin")
    assert bound.assignments_created == 1
    again = await platform_seed.seed_platform_rbac(platform_code="platform", assign_user="admin")
    assert again.assignments_skipped == 1
    missing = await platform_seed.seed_platform_rbac(platform_code="platform", assign_user="ghost")
    assert missing.assignments_created == 0


@pytest.mark.kiwi_id(2343)
def test_main_dry_run_prints_plan(capsys: pytest.CaptureFixture[str]) -> None:
    """`--dry-run` 只打印角色与业务码清单，不建连。"""
    assert platform_seed.main(ConcurrentStableList(["--code", "platform", "--dry-run"])) == 0
    out = capsys.readouterr().out
    assert "[seed_platform] 平台租户 platform" in out
    assert platform_seed.PLATFORM_ADMIN_ROLE_CODE in out
    assert "平台业务码" in out


@pytest.mark.kiwi_id(2343)
def test_build_parser_defaults() -> None:
    """CLI 缺省值：编码取配置、绑定账号 admin、不预演。"""
    args = platform_seed.build_parser().parse_args([])
    assert args.code == ""
    assert args.assign_user == "admin"
    assert args.dry_run is False


@pytest.mark.kiwi_id(2343)
def test_constants() -> None:
    """常量与授权清单口径（运维角色只读、业务码范围固定）。"""
    assert platform_seed.PLATFORM_ADMIN_ROLE_CODE == "platform_admin"
    assert platform_seed.PLATFORM_OPS_ROLE_CODE == "platform_ops"
    assert platform_seed.PLATFORM_TENANT_MENU_PATH == "/platform/tenants"
    assert tuple(platform_seed.PLATFORM_BUSINESS_CODES) == _BUSINESSES
    assert all(code.endswith(":query") for code in platform_seed.PLATFORM_OPS_PERMISSION_CODES)
