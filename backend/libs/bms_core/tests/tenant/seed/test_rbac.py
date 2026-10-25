"""内置角色与授权种子用例（14_04 自 `services/platform/tests/seed/test_seed_rbac.py` 迁入基座）。

覆盖 `bms_core/tenant/seed/rbac.py`：幂等、缺码跳过、三权清单边界、预演不落库、三权互斥拒绝绑定、
CLI 打印与退出码。
"""

import argparse
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import Base
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import SEPARATION_ROLE_TYPES, SysRole, SysRolePermission, SysUserRole
from bms_core.models.platform.user import SysUser
from bms_core.tenant.seed.rbac import (
    AUDIT_ADMIN_CODES,
    BUILTIN_ADMIN_ROLES,
    ROLE_AUDIT_ADMIN,
    ROLE_SECURITY_ADMIN,
    ROLE_SYSTEM_ADMIN,
    SECURITY_ADMIN_CODES,
    SYSTEM_ADMIN_CODES,
    build_parser,
    main,
    seed_rbac,
)

_BUSINESSES = (("menu", "菜单管理"), ("role", "角色管理"))
_PERMISSIONS = (("menu", "query"), ("menu", "create"), ("role", "query"), ("role", "grant"))


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
    ]
    async with platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=platform_tables))
    factory = async_sessionmaker(platform_engine, expire_on_commit=False)
    async with factory() as session:
        by_code: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for code, name in _BUSINESSES:
            row = SysBusiness(code=code, name=name)
            session.add(row)
            await session.flush()
            by_code.set(code, int(row.id))
        action_ids: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        for business, action in _PERMISSIONS:
            if action not in action_ids:
                action_row = SysAction(code=action, name=action)
                session.add(action_row)
                await session.flush()
                action_ids.set(action, int(action_row.id))
            session.add(SysPermission(business_id=by_code[business], action_id=action_ids[action]))
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
                mapping.set(role.code, int(role.id))
            return mapping, len(grants)
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2269)
async def test_seed_creates_builtin_roles_and_grants_idempotently(urls: tuple[str, str]) -> None:
    """首次播种建三类内置角色与在册授权；重复执行全跳过（幂等）。"""
    tenant_url, platform_url = urls
    first = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert first.roles_created == 3
    assert first.roles_skipped == 0
    assert first.grants_created == 4  # 平台库登记了 4 个权限码：menu:query / menu:create / role:query / role:grant
    codes, grants = await _roles_and_grants(tenant_url)
    assert set(codes) == {ROLE_SYSTEM_ADMIN, ROLE_SECURITY_ADMIN, ROLE_AUDIT_ADMIN}
    assert grants == 4
    assert first.missing_codes  # 其余在册码平台库未登记 → 上报且不产生授权
    assert set(SECURITY_ADMIN_CODES).issubset(set(SYSTEM_ADMIN_CODES) | set(SECURITY_ADMIN_CODES))
    assert set(AUDIT_ADMIN_CODES) == set()
    # `02_01` 用户完整域：系统管理员持全部用户域码（防新端点 403 自锁）
    assert {
        "user:create",
        "user:update",
        "user:delete",
        "user:reset_pwd",
        "user:assign_role",
    } <= set(SYSTEM_ADMIN_CODES)

    second = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert (second.roles_created, second.grants_created) == (0, 0)
    assert second.roles_skipped == 3
    assert second.grants_skipped == 4
    _, grants_after = await _roles_and_grants(tenant_url)
    assert grants_after == 4


@pytest.mark.kiwi_id(2314)
def test_builtin_admin_roles_come_from_separation_single_source() -> None:
    """三类内置管理员角色来自 `SEPARATION_ROLE_TYPES` 单一来源，且角色域码只归安全管理员（需求 07-6）。

    `03_02` 口径：`BUILTIN_ADMIN_ROLES` 是「三类内置角色 + 授权清单」的唯一来源（开通种子直接引用）；
    `role_type` 三值必须与模型常量 `SEPARATION_ROLE_TYPES` 完全一致，互斥校验才成立。
    """
    assert tuple(entry[2] for entry in BUILTIN_ADMIN_ROLES) == SEPARATION_ROLE_TYPES
    assert tuple(entry[0] for entry in BUILTIN_ADMIN_ROLES) == (
        ROLE_SYSTEM_ADMIN,
        ROLE_SECURITY_ADMIN,
        ROLE_AUDIT_ADMIN,
    )
    role_codes = {code for code in SECURITY_ADMIN_CODES if code.startswith("role:")}
    assert role_codes == {"role:query", "role:create", "role:update", "role:delete", "role:grant"}
    # 系统 / 审计管理员不得持有角色域权限码（`role` 业务仅安全管理员）
    assert not [code for code in SYSTEM_ADMIN_CODES if code.startswith("role:")]
    assert not [code for code in AUDIT_ADMIN_CODES if code.startswith("role:")]


@pytest.mark.kiwi_id(2314)
async def test_seed_refuses_assignment_conflicting_with_separation(urls: tuple[str, str]) -> None:
    """种子绑定 bootstrap 账号前复用三权互斥口径：账号已持另一类内置管理员即拒绝绑定。

    `_ensure_assignment` 与 `SeparationGuard.ensure_role_grant_exclusive`（服务层 `30010`）同一判定，
    种子不绕过护栏——已持安全管理员角色的账号不会被再绑到系统管理员。
    """
    tenant_url, platform_url = urls
    first = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert first.roles_created == 3
    codes, _ = await _roles_and_grants(tenant_url)

    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = SysUser(username="seed_admin", password_hash="x", name="种子管理员")
            session.add(user)
            await session.flush()
            session.add(SysUserRole(role_id=codes[ROLE_SECURITY_ADMIN], user_id=user.id))
            await session.commit()
    finally:
        await engine.dispose()

    second = await seed_rbac(
        tenant_url=tenant_url,
        platform_url=platform_url,
        assign_user="seed_admin",
    )
    assert list(second.assign_conflicts) == ["seed_admin"]
    assert second.assignments_created == 0
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            bindings = (
                (await session.execute(select(SysUserRole).where(SysUserRole.deleted_at.is_(None)))).scalars().all()
            )
            assert {binding.role_id for binding in bindings} == {codes[ROLE_SECURITY_ADMIN]}
    finally:
        await engine.dispose()


@pytest.mark.kiwi_id(2269)
async def test_seed_dry_run_does_not_write(urls: tuple[str, str]) -> None:
    """预演模式只报计划、不落库。"""
    tenant_url, platform_url = urls
    outcome = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, dry_run=True)
    assert outcome.roles_created == 3
    codes, grants = await _roles_and_grants(tenant_url)
    assert codes == {}
    assert grants == 0


@pytest.mark.kiwi_id(2343)
async def test_seed_assigns_user_by_username_and_skips_when_already_bound(urls: tuple[str, str]) -> None:
    """`assign_user` 命中账号时绑定成功；已绑定账号再跑记「跳过」；纯数字按用户主键解析。"""
    tenant_url, platform_url = urls
    await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = SysUser(username="boot_admin", password_hash="x", name="引导管理员")
            session.add(user)
            await session.flush()
            user_id = int(user.id)
            await session.commit()
    finally:
        await engine.dispose()

    created = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, assign_user="boot_admin")
    assert created.assignments_created == 1
    assert created.assignments_skipped == 0
    assert list(created.assign_unresolved) == []

    again = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, assign_user="boot_admin")
    assert again.assignments_created == 0
    assert again.assignments_skipped == 1

    by_id = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, assign_user=str(user_id))
    assert by_id.assignments_skipped == 1

    missing = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url, assign_user="ghost")
    assert list(missing.assign_unresolved) == ["ghost"]


@pytest.mark.kiwi_id(2343)
async def test_seed_skips_missing_permission_codes(urls: tuple[str, str]) -> None:
    """平台库未登记的权限码被跳过并上报，且不产生授权行。"""
    tenant_url, platform_url = urls
    outcome = await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    assert "user:create" in outcome.missing_codes
    _, grants = await _roles_and_grants(tenant_url)
    assert grants == outcome.grants_created == 4


@pytest.mark.kiwi_id(2343)
async def test_main_prints_outcome(urls: tuple[str, str], capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：打印两库目标与执行汇总；`--assign-user` 触发绑定行打印；缺码 / 未解析 / 互斥各有提示。"""
    tenant_url, platform_url = urls
    args = build_parser().parse_args(
        [
            "--tenant",
            "demo",
            "--tenant-url",
            tenant_url,
            "--platform-url",
            platform_url,
            "--assign-user",
            "ghost",
        ]
    )
    await main(args)
    out = capsys.readouterr().out
    assert "[seed_rbac] 租户库（角色域）：" in out
    assert "[seed_rbac] 服务库（权限码）：" in out
    assert "落库完成" in out
    assert "绑定内置系统管理员：ghost" in out
    assert "待绑定但库中未找到" in out
    assert "平台库未登记、已跳过的权限码" in out


@pytest.mark.kiwi_id(2343)
async def test_main_dry_run_and_conflict_messages(urls: tuple[str, str], capsys: pytest.CaptureFixture[str]) -> None:
    """CLI：`--dry-run` 打印「预演完成」不落库；三权互斥拒绝绑定时打印拒绝提示。"""
    tenant_url, platform_url = urls
    dry = build_parser().parse_args(
        ["--tenant", "demo", "--tenant-url", tenant_url, "--platform-url", platform_url, "--dry-run"]
    )
    await main(dry)
    assert "预演完成" in capsys.readouterr().out
    codes, grants = await _roles_and_grants(tenant_url)
    assert codes == {}
    assert grants == 0

    await seed_rbac(tenant_url=tenant_url, platform_url=platform_url)
    codes, _ = await _roles_and_grants(tenant_url)
    engine = create_async_engine(tenant_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = SysUser(username="sep_admin", password_hash="x", name="互斥管理员")
            session.add(user)
            await session.flush()
            session.add(SysUserRole(role_id=codes[ROLE_SECURITY_ADMIN], user_id=user.id))
            await session.commit()
    finally:
        await engine.dispose()
    conflict = build_parser().parse_args(
        [
            "--tenant",
            "demo",
            "--tenant-url",
            tenant_url,
            "--platform-url",
            platform_url,
            "--assign-user",
            "sep_admin",
        ]
    )
    await main(conflict)
    assert "三权互斥、已拒绝绑定的账号" in capsys.readouterr().out


@pytest.mark.kiwi_id(2343)
def test_build_parser_defaults() -> None:
    """CLI 缺省值：租户 demo / 服务 platform / 不绑定 / 不预演。"""
    args = build_parser().parse_args([])
    assert args.tenant == "demo"
    assert args.service == "platform"
    assert args.assign_user == ""
    assert args.dry_run is False
    assert isinstance(args, argparse.Namespace)


def test_module_exports() -> None:
    """公开符号齐备（薄壳与开通内核按名引用）。"""
    assert ROLE_SYSTEM_ADMIN == "system_admin"
    assert ROLE_SECURITY_ADMIN == "security_admin"
    assert ROLE_AUDIT_ADMIN == "audit_admin"
    assert set(SECURITY_ADMIN_CODES) == {"role:query", "role:create", "role:update", "role:delete", "role:grant"}
    assert len(BUILTIN_ADMIN_ROLES) == 3
    assert ConcurrentStableList(AUDIT_ADMIN_CODES) == ConcurrentStableList()
