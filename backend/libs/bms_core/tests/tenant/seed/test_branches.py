"""下沉模块剩余分支补测（Kiwi 2343）：条件假分支与「无缺码 / 无口令」路径。

补齐：
- `seed/platform.py`：权限码行的业务或动作缺失（映射跳过）；
- `seed/rbac.py`：同一缺码重复出现（去重分支）、权限码行缺业务或动作、**无缺码**时的 CLI 输出；
- `seed/sso.py`：正常路径不带映射；
- `seed/user.py`：既有账号且未重置（无口令打印）。
"""

from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SysRole, SysRolePermission, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.tenant.seed import platform as platform_seed
from bms_core.tenant.seed import rbac as rbac_seed
from bms_core.tenant.seed import sso as sso_seed
from bms_core.tenant.seed import user as user_seed


async def _platform_db_with_dangling_permission(path: Path) -> str:
    """建平台库：含一条业务 / 动作悬空的权限码行（映射时被跳过）。

    Args:
        path: 库文件路径。

    Returns:
        str: 平台库连接串。
    """
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url)
    tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        business = SysBusiness(code="menu", name="菜单管理")
        action = SysAction(code="query", name="查询")
        session.add_all([business, action])
        await session.flush()
        session.add(SysPermission(business_id=int(business.id), action_id=int(action.id)))
        # 悬空行：business_id / action_id 指向不存在的行
        session.add(SysPermission(business_id=999_999, action_id=999_999))
        await session.commit()
    await engine.dispose()
    return url


@pytest.mark.kiwi_id(2343)
async def test_rbac_skips_dangling_permission_rows(tmp_path: Path) -> None:
    """权限码行业务 / 动作悬空时被跳过（`business_code and action_code` 假分支）。"""
    platform_url = await _platform_db_with_dangling_permission(tmp_path / "platform.db")
    ids = await rbac_seed._load_permission_ids(platform_url)  # pyright: ignore[reportPrivateUsage]
    assert dict(ids) == {"menu:query": ids.get("menu:query")}


@pytest.mark.kiwi_id(2343)
async def test_rbac_dedupes_repeated_missing_codes(tmp_path: Path) -> None:
    """同一缺码在多个角色清单中重复出现时只登记一次（去重假分支）。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(tenant_url)
    tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysUser.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    await engine.dispose()
    platform_engine = create_async_engine(platform_url)
    platform_tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
    ]
    async with platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
    await platform_engine.dispose()

    # 让两个角色的清单共享同一缺码（临时替换内置清单）
    shared = ConcurrentStableList(["role:query"])
    original = rbac_seed.BUILTIN_ADMIN_ROLES
    rbac_seed.BUILTIN_ADMIN_ROLES = ConcurrentStableList(
        [
            (rbac_seed.ROLE_SYSTEM_ADMIN, "系统管理员", "system", shared),
            (rbac_seed.ROLE_SECURITY_ADMIN, "安全管理员", "security", shared),
        ]
    )
    try:
        outcome = await rbac_seed.seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    finally:
        rbac_seed.BUILTIN_ADMIN_ROLES = original
    assert list(outcome.missing_codes).count("role:query") == 1


@pytest.mark.kiwi_id(2343)
async def test_rbac_main_without_missing_codes_prints_no_missing_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """平台库码齐备时 CLI 不打印缺码行（`missing_codes` 空分支）。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(tenant_url)
    tables = [
        cast("Table", SysRole.__table__),
        cast("Table", SysRolePermission.__table__),
        cast("Table", SysUserRole.__table__),
        cast("Table", SysUser.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    await engine.dispose()
    platform_engine = create_async_engine(platform_url)
    platform_tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
    ]
    async with platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
    await platform_engine.dispose()

    original = rbac_seed.BUILTIN_ADMIN_ROLES
    rbac_seed.BUILTIN_ADMIN_ROLES = ConcurrentStableList(
        [(rbac_seed.ROLE_SYSTEM_ADMIN, "系统管理员", "system", ConcurrentStableList())]
    )
    try:
        args = rbac_seed.build_parser().parse_args(
            ["--tenant", "demo", "--tenant-url", tenant_url, "--platform-url", platform_url]
        )
        await rbac_seed.main(args)
    finally:
        rbac_seed.BUILTIN_ADMIN_ROLES = original
    out = capsys.readouterr().out
    assert "落库完成" in out
    assert "平台库未登记、已跳过的权限码" not in out


@pytest.mark.kiwi_id(2343)
async def test_seed_platform_skips_dangling_permission_rows(tmp_path: Path) -> None:
    """平台 RBAC 种子：业务 / 动作悬空的权限码行被跳过（不产生 `code:action` 映射）。"""
    platform_url = await _platform_db_with_dangling_permission(tmp_path / "platform.db")
    ids = await platform_seed._permission_ids(platform_url)  # pyright: ignore[reportPrivateUsage]
    assert dict(ids) == {"menu:query": ids.get("menu:query")}


@pytest.mark.kiwi_id(2343)
async def test_seed_platform_skips_rows_with_missing_action(tmp_path: Path) -> None:
    """业务存在但动作悬空（`action is None`）：该行被跳过，其余行照常映射。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(url)
    tables = [
        cast("Table", SysBusiness.__table__),
        cast("Table", SysAction.__table__),
        cast("Table", SysPermission.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        business = SysBusiness(code="menu", name="菜单管理")
        action = SysAction(code="query", name="查询")
        session.add_all([business, action])
        await session.flush()
        session.add(SysPermission(business_id=int(business.id), action_id=int(action.id)))
        session.add(SysPermission(business_id=int(business.id), action_id=999_999))
        await session.commit()
    await engine.dispose()

    ids = await platform_seed._permission_ids(url)  # pyright: ignore[reportPrivateUsage]
    assert list(ids) == ["menu:query"]


@pytest.mark.kiwi_id(2343)
def test_sso_main_without_mapping(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`seed_sso.main` 正常路径不带映射：只写 IdP 行，不打印用户映射行。"""
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}"
    assert sso_seed.main(ConcurrentStableList(["--url", tenant_url])) == 0
    out = capsys.readouterr().out
    assert "IdP 行新增 1 行" in out
    assert "用户映射新增" not in out


@pytest.mark.kiwi_id(2343)
def test_user_main_skips_password_line_for_existing_account(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """既有账号且未重置：不打印口令行（`outcome.password` 空分支）。"""
    url = f"sqlite+aiosqlite:///{tmp_path}/platform.db"
    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin"])) == 0
    capsys.readouterr()
    assert user_seed.main(ConcurrentStableList(["--url", url, "--username", "admin"])) == 0
    out = capsys.readouterr().out
    assert "跳过 1 行" in out
    assert "口令（仅本次打印" not in out
