"""平台租户 RBAC 种子（幂等）：`platform_admin` / `platform_ops` 角色与授权、初始超管绑定（任务 `04_01`）。

用法：

```bash
cd backend
uv run python -m ops.seed_platform --dry-run
uv run python -m ops.seed_platform
uv run python -m ops.seed_platform --assign-user admin
```

- **库定位**：租户库 = platform 服务租户库 `bms_platform_{platform_code}`（角色域）；
  平台库 = `bms_platform`（`sys_business` / `sys_permission` / `sys_menu` / `sys_form`）。
- **角色**：`platform_admin`（`role_type=platform_admin`，全权限豁免 + 平台业务全部权限码授权）、
  `platform_ops`（`role_type=custom`，只读运维：平台业务 query 权限码 + 租户管理菜单 / 表单入口）。
- **幂等**：角色按 `code` 判存、授权按四元组判存、绑定按 `(role_id, user_id)` 判存；重复执行为 0 新增。
"""

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import build_platform_db_key, build_tenant_db_key
from bms_core.models.platform.menu import SysAction, SysBusiness, SysForm, SysMenu, SysPermission
from bms_core.models.platform.role import (
    NO_SOURCE_MENU_ID,
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    ROLE_TYPE_CUSTOM,
    ROLE_TYPE_PLATFORM_ADMIN,
    SysRole,
    SysRolePermission,
    SysUserRole,
)
from bms_core.models.platform.user import SysUser

__all__ = [
    "PLATFORM_ADMIN_ROLE_CODE",
    "PLATFORM_BUSINESS_CODES",
    "PLATFORM_OPS_PERMISSION_CODES",
    "PLATFORM_OPS_ROLE_CODE",
    "PlatformSeedOutcome",
    "seed_platform_rbac",
]

PLATFORM_ADMIN_ROLE_CODE = "platform_admin"
"""平台超管角色码。"""

PLATFORM_OPS_ROLE_CODE = "platform_ops"
"""平台运维（只读）角色码。"""

PLATFORM_BUSINESS_CODES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "sys",
        "tenant",
        "menu",
        "business",
        "action",
        "permission",
        "user-extension",
    )
)
"""平台业务码（平台超管的授权范围；来源《架构设计 · 权限计算引擎》§7）。"""

PLATFORM_OPS_PERMISSION_CODES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "sys:query",
        "tenant:query",
        "menu:query",
        "business:query",
        "action:query",
        "permission:query",
    )
)
"""平台运维角色只读权限码。"""

PLATFORM_TENANT_MENU_PATH = "/platform/tenants"
"""租户管理菜单路径（运维角色入口授权）。"""


@dataclass
class PlatformSeedOutcome:
    """平台 RBAC 种子结果。"""

    roles_created: int = 0
    roles_skipped: int = 0
    grants_created: int = 0
    grants_skipped: int = 0
    assignments_created: int = 0
    assignments_skipped: int = 0


def _urls(platform_code: str) -> tuple[str, str]:
    """解析租户库与平台库连接串。

    Args:
        platform_code: 平台租户编码。

    Returns:
        tuple[str, str]: (platform 服务租户库, platform 服务平台库)。
    """
    factory = EngineFactory(get_settings(), allow_cross_service=True)
    return (
        factory.resolved_url(build_tenant_db_key(platform_code, service="platform")),
        factory.resolved_url(build_platform_db_key("platform")),
    )


async def _permission_ids(platform_url: str) -> ConcurrentStableDict[str, int]:
    """取平台业务权限码 id 映射（`业务码:动作码` → `sys_permission.id`）。

    Args:
        platform_url: platform 服务平台库连接串。

    Returns:
        ConcurrentStableDict[str, int]: 权限码 → id。
    """
    engine = create_async_engine(platform_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            businesses = {
                row.code: row
                for row in (
                    await session.execute(
                        select(SysBusiness).where(
                            SysBusiness.code.in_(PLATFORM_BUSINESS_CODES), SysBusiness.deleted_at.is_(None)
                        )
                    )
                )
                .scalars()
                .all()
            }
            actions = {
                row.id: row.code
                for row in (await session.execute(select(SysAction).where(SysAction.deleted_at.is_(None))))
                .scalars()
                .all()
            }
            rows = (
                (
                    await session.execute(
                        select(SysPermission).where(
                            SysPermission.business_id.in_([item.id for item in businesses.values()]),
                            SysPermission.deleted_at.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            result: ConcurrentStableDict[str, int] = ConcurrentStableDict()
            for row in rows:
                business = next((item for item in businesses.values() if item.id == row.business_id), None)
                action = actions.get(row.action_id)
                if business is not None and action is not None:
                    result[f"{business.code}:{action}"] = int(row.id)
            return result
    finally:
        await engine.dispose()


async def _entry_targets(platform_url: str) -> tuple[ConcurrentStableList[int], ConcurrentStableList[int]]:
    """取平台运维角色的菜单 / 表单入口授权目标。

    Args:
        platform_url: platform 服务平台库连接串。

    Returns:
        tuple[ConcurrentStableList[int], ConcurrentStableList[int]]: (菜单 id 清单, 表单 id 清单)。
    """
    engine = create_async_engine(platform_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            paths = ("/platform", PLATFORM_TENANT_MENU_PATH)
            menus = ConcurrentStableList[int](
                int(row.id)
                for row in (
                    await session.execute(select(SysMenu).where(SysMenu.path.in_(paths), SysMenu.deleted_at.is_(None)))
                )
                .scalars()
                .all()
            )
            business = (
                await session.execute(
                    select(SysBusiness).where(SysBusiness.code == "tenant", SysBusiness.deleted_at.is_(None))
                )
            ).scalar_one_or_none()
            forms = ConcurrentStableList[int]()
            if business is not None:
                forms = ConcurrentStableList(
                    int(row.id)
                    for row in (
                        await session.execute(
                            select(SysForm).where(SysForm.business_id == int(business.id), SysForm.deleted_at.is_(None))
                        )
                    )
                    .scalars()
                    .all()
                )
            return menus, forms
    finally:
        await engine.dispose()


async def _ensure_role(
    session: AsyncSession, *, code: str, name: str, role_type: str, outcome: PlatformSeedOutcome
) -> int:
    """取或建角色（按 `code` 判存）。

    Args:
        session: 租户库会话。
        code: 角色码。
        name: 角色名称。
        role_type: 角色类型。
        outcome: 结果累计。

    Returns:
        int: 角色主键。
    """
    existing = (
        await session.execute(select(SysRole).where(SysRole.code == code, SysRole.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if existing is not None:
        outcome.roles_skipped += 1
        return int(existing.id)
    role = SysRole(code=code, name=name, status="enabled", role_type=role_type)
    session.add(role)
    await session.flush()
    outcome.roles_created += 1
    return int(role.id)


async def _ensure_grant(
    session: AsyncSession, *, role_id: int, perm_type: str, target_id: int, outcome: PlatformSeedOutcome
) -> None:
    """取或建授权条目（按四元组判存）。

    Args:
        session: 租户库会话。
        role_id: 角色主键。
        perm_type: 授权类型（menu / form / permission）。
        target_id: 目标主键。
        outcome: 结果累计。
    """
    existing = (
        await session.execute(
            select(SysRolePermission).where(
                SysRolePermission.role_id == role_id,
                SysRolePermission.perm_type == perm_type,
                SysRolePermission.target_id == target_id,
                SysRolePermission.source_menu_id == NO_SOURCE_MENU_ID,
                SysRolePermission.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        outcome.grants_skipped += 1
        return
    session.add(
        SysRolePermission(role_id=role_id, perm_type=perm_type, target_id=target_id, source_menu_id=NO_SOURCE_MENU_ID)
    )
    await session.flush()
    outcome.grants_created += 1


async def _ensure_assignment(
    session: AsyncSession, *, role_id: int, user_id: int, outcome: PlatformSeedOutcome
) -> None:
    """取或建「用户 → 角色」绑定。

    Args:
        session: 租户库会话。
        role_id: 角色主键。
        user_id: 用户主键。
        outcome: 结果累计。
    """
    existing = (
        await session.execute(
            select(SysUserRole).where(
                SysUserRole.role_id == role_id, SysUserRole.user_id == user_id, SysUserRole.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        outcome.assignments_skipped += 1
        return
    session.add(SysUserRole(role_id=role_id, user_id=user_id))
    await session.flush()
    outcome.assignments_created += 1


async def seed_platform_rbac(*, platform_code: str, assign_user: str = "") -> PlatformSeedOutcome:
    """播种平台租户 RBAC（两个角色 + 授权 + 可选绑定）。

    Args:
        platform_code: 平台租户编码。
        assign_user: 待绑定到 `platform_admin` 的账号（`sys_user.code`；空串跳过）。

    Returns:
        PlatformSeedOutcome: 执行结果。
    """
    tenant_url, platform_url = _urls(platform_code)
    permissions = await _permission_ids(platform_url)
    menus, forms = await _entry_targets(platform_url)
    outcome = PlatformSeedOutcome()
    engine = create_async_engine(tenant_url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            admin_role = await _ensure_role(
                session,
                code=PLATFORM_ADMIN_ROLE_CODE,
                name="平台超级管理员",
                role_type=ROLE_TYPE_PLATFORM_ADMIN,
                outcome=outcome,
            )
            ops_role = await _ensure_role(
                session,
                code=PLATFORM_OPS_ROLE_CODE,
                name="平台运维员",
                role_type=ROLE_TYPE_CUSTOM,
                outcome=outcome,
            )
            for permission_id in permissions.values():
                await _ensure_grant(
                    session,
                    role_id=admin_role,
                    perm_type=PERM_TYPE_PERMISSION,
                    target_id=permission_id,
                    outcome=outcome,
                )
            for code in PLATFORM_OPS_PERMISSION_CODES:
                permission_id = permissions.get(code)
                if permission_id is None:
                    continue
                await _ensure_grant(
                    session, role_id=ops_role, perm_type=PERM_TYPE_PERMISSION, target_id=permission_id, outcome=outcome
                )
            for menu_id in menus:
                await _ensure_grant(
                    session, role_id=ops_role, perm_type=PERM_TYPE_MENU, target_id=menu_id, outcome=outcome
                )
            for form_id in forms:
                await _ensure_grant(
                    session, role_id=ops_role, perm_type=PERM_TYPE_FORM, target_id=form_id, outcome=outcome
                )
            if assign_user:
                user = (
                    await session.execute(
                        select(SysUser).where(SysUser.username == assign_user, SysUser.deleted_at.is_(None))
                    )
                ).scalar_one_or_none()
                if user is not None:
                    await _ensure_assignment(session, role_id=admin_role, user_id=int(user.id), outcome=outcome)
            await session.commit()
    finally:
        await engine.dispose()
    return outcome


def build_parser() -> argparse.ArgumentParser:
    """构建命令行解析器。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(description="平台租户 RBAC 种子（platform_admin / platform_ops，幂等）")
    parser.add_argument("--code", default="", help="平台租户编码（缺省取 [platform_tenant].code）")
    parser.add_argument("--assign-user", default="admin", help="绑定到平台超管角色的账号（空串跳过）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印目标与清单（不建连）")
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数。

    Returns:
        int: 退出码。
    """
    args = build_parser().parse_args(argv)
    code = args.code or get_settings().platform_tenant.code
    if args.dry_run:
        print(f"[seed_platform] 平台租户 {code}：角色 {PLATFORM_ADMIN_ROLE_CODE} / {PLATFORM_OPS_ROLE_CODE}")
        print(f"[seed_platform] 平台业务码：{'、'.join(PLATFORM_BUSINESS_CODES)}")
        return 0
    outcome = asyncio.run(seed_platform_rbac(platform_code=code, assign_user=args.assign_user))
    print(
        f"[seed_platform] 角色新增 {outcome.roles_created} / 跳过 {outcome.roles_skipped}；"
        f"授权新增 {outcome.grants_created} / 跳过 {outcome.grants_skipped}；"
        f"绑定新增 {outcome.assignments_created} / 跳过 {outcome.assignments_skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
