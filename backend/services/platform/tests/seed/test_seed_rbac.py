"""内置角色授权种子用例（`02_04`）：幂等、缺码跳过、三权清单边界、预演不落库。

覆盖：两库协同（平台库动作码 → 租户库角色 / 授权）、重复执行全跳过、平台库未登记码**不产生授权**
并上报、`--dry-run` 只读不写。
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.base import Base
from bms_platform.models.menu import SysAction, SysBusiness
from bms_platform.models.role import SysRole, SysRolePermission
from ops.seed_rbac import (
    AUDIT_ADMIN_CODES,
    ROLE_AUDIT_ADMIN,
    ROLE_SECURITY_ADMIN,
    ROLE_SYSTEM_ADMIN,
    SECURITY_ADMIN_CODES,
    SYSTEM_ADMIN_CODES,
    seed_rbac,
)

_BUSINESSES = (("menu", "菜单管理"), ("role", "角色管理"))
_ACTIONS = (("menu", "query"), ("menu", "create"), ("role", "query"), ("role", "grant"))


@pytest_asyncio.fixture
async def urls(tmp_path: Path) -> AsyncIterator[tuple[str, str]]:
    """建两库并播种业务 / 动作码（平台库）与角色域表（租户库）。

    Args:
        tmp_path: pytest 临时目录。

    Yields:
        tuple[str, str]: （租户库 URL，平台库 URL）。
    """
    tenant_url = f"sqlite+aiosqlite:///{tmp_path / 'tenant.db'}"
    platform_url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    tenant_engine = create_async_engine(tenant_url)
    tenant_tables = [SysRole.__table__, SysRolePermission.__table__]
    async with tenant_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tenant_tables))
    await tenant_engine.dispose()
    platform_engine = create_async_engine(platform_url)
    platform_tables = [SysBusiness.__table__, SysAction.__table__]
    async with platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    async with factory() as session:
        by_code = {}
        for code, name in _BUSINESSES:
            row = SysBusiness(code=code, name=name)
            session.add(row)
            await session.flush()
            by_code[code] = row.id
        for business, action in _ACTIONS:
            session.add(SysAction(code=action, name=action, business_id=by_code[business]))
        await session.commit()
    await platform_engine.dispose()
    yield tenant_url, platform_url


async def _roles_and_grants(url: str) -> tuple[ConcurrentStableDict[str, int], int]:
    """读取角色（code → id）与授权条目总数。

    Args:
        url: 租户库连接串。

    Returns:
        tuple[ConcurrentStableDict[str, int], int]: （角色码映射，授权条目数）。
    """
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            roles = (await session.execute(select(SysRole))).scalars().all()
            grants = (await session.execute(select(SysRolePermission))).scalars().all()
            mapping: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for role in roles:
                mapping.set(role.code, role.id)
            return mapping, len(grants)
    finally:
        await engine.dispose()


async def test_seed_creates_builtin_roles_and_grants_idempotently(urls: tuple[str, str]) -> None:
    """首次播种建三类内置角色与在册授权；重复执行全跳过（幂等）。"""
    tenant_url, platform_url = urls
    first = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert first.roles_created == 3
    assert first.roles_skipped == 0
    assert first.grants_created == 4  # 平台库登记了 4 个动作码：menu:query / menu:create / role:query / role:grant
    codes, grants = await _roles_and_grants(tenant_url)
    assert set(codes) == {ROLE_SYSTEM_ADMIN, ROLE_SECURITY_ADMIN, ROLE_AUDIT_ADMIN}
    assert grants == 4
    assert first.missing_codes  # 其余在册码平台库未登记 → 上报且不产生授权
    assert set(SECURITY_ADMIN_CODES).issubset(set(SYSTEM_ADMIN_CODES) | set(SECURITY_ADMIN_CODES))
    assert set(AUDIT_ADMIN_CODES) == set()

    second = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert (second.roles_created, second.grants_created) == (0, 0)
    assert second.roles_skipped == 3
    assert second.grants_skipped == 4
    _, grants_after = await _roles_and_grants(tenant_url)
    assert grants_after == 4


async def test_seed_dry_run_does_not_write(urls: tuple[str, str]) -> None:
    """预演模式只报计划、不落库。"""
    tenant_url, platform_url = urls
    outcome = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, dry_run=True)
    assert outcome.roles_created == 3
    codes, grants = await _roles_and_grants(tenant_url)
    assert codes == {}
    assert grants == 0
