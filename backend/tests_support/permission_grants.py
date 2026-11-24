"""真实授权装配（测试支持）：最小菜单元数据 + 自定义角色授权。

P5 口径（13_10）：用例不再替换权限检查器（`dependency_overrides[get_permission_checker]`），
而是像真实运行一样**准备授权数据**，让校验走真实 RBAC：

- **平台库**：业务码 / 动作码 / 权限码，以及一条「权限装配」菜单（菜单 → 表单 → 按钮）。
  权限快照的「权限码 id → 码」索引**只从按钮产生**（`_index_metadata` 遍历菜单表单按钮），
  所以每条要用的权限码都必须挂一个按钮，否则授予了也解析不出码。
- **租户库**：自定义角色（`role_type=custom`，**不属豁免层级**）+ 权限码授权 + 用户绑定。

权限码字符串是「业务码:动作码」（如 `export:download` 对应 `sys_business.code=export` +
`sys_action.code=download` 的 `sys_permission` 行）。全部按 code 幂等：共享库跨轮次叠加，
已有行一律复用（业务码 / 动作码 / 权限码 / 菜单 / 表单 / 按钮 / 角色 / 授权 / 绑定）。

**缓存**：应用装配的缓存 Region 是插件级实例、跨用例复用，写库后必须让参数/菜单/权限快照
一起失效——`reset_permission_state` 在首次请求前调用一次（清通用缓存域 + 进程级快照仓）。
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.platform.menu_form import SysButton, SysForm, SysMenu, SysMenuForm
from bms_core.models.platform.permission_meta import SysAction, SysBusiness, SysPermission
from bms_core.models.platform.role import (
    PERM_TYPE_PERMISSION,
    ROLE_TYPE_CUSTOM,
    SysRole,
    SysRolePermission,
    SysUserRole,
)
from bms_core.permission.cache import reset_permission_cache_store
from tests_support.shared_access import shared_session

__all__ = [
    "DATA_PLAIN",
    "EXPORT_DOWNLOAD",
    "IMPORT_EXECUTE",
    "ensure_permissions",
    "grant_permissions",
    "platform_url",
    "reset_permission_state",
    "tenant_url",
]

EXPORT_DOWNLOAD = "export:download"
"""导出下载入口权限码。"""

IMPORT_EXECUTE = "import:execute"
"""导入执行入口权限码。"""

DATA_PLAIN = "data:plain"
"""敏感字段明文查看权限码。"""

_PERMISSION_MENU_PATH = "/__test/permission-grants"
"""测试权限装配菜单路径（全库一份，按路径幂等复用）。"""

_PERMISSION_MENU_NAME = "测试权限装配"
"""测试权限装配菜单名。"""


def platform_url() -> str:
    """当前用例的平台库连接串（由测试公共基座的 `platform_db` 夹具注入）。

    Returns:
        str: 平台库连接串。
    """
    return os.environ["BMS_DATABASE__PLATFORM__URL"]


def tenant_url() -> str:
    """当前用例的租户库连接串（由各服务夹具注入）。

    Returns:
        str: 租户库连接串。
    """
    return os.environ["BMS_DATABASE__TENANTS__URL"]


async def ensure_permissions(codes: ConcurrentStableList[str]) -> ConcurrentStableDict[str, int]:
    """确保每条权限码在平台库可用（业务码 / 动作码 / 权限码 / 菜单按钮），返回码 → 权限码主键。

    Args:
        codes: 权限码清单（`业务码:动作码`）。

    Returns:
        ConcurrentStableDict[str, int]: 权限码 → `sys_permission` 主键（插入序）。
    """
    result: ConcurrentStableDict[str, int] = ConcurrentStableDict()
    if not codes:
        return result
    async with shared_session(platform_url(), read_only=False) as session:
        menu = await _menu_row(session)
        first_business_id = 0
        for code in codes:
            business_code, action_code = code.split(":", 1)
            business_id = await _business_id(session, business_code)
            if not first_business_id:
                first_business_id = business_id
            action_id = await _action_id(session, action_code)
            permission_id = await _permission_id(session, business_id=business_id, action_id=action_id)
            form_id = await _form_id(session, menu_id=menu.id, business_id=first_business_id)
            await _button(session, form_id=form_id, permission_id=permission_id, name=code)
            result.set(code, permission_id)
        await session.commit()
    return result


async def grant_permissions(user_id: int, codes: ConcurrentStableList[str], *, role_code: str) -> int:
    """给主体授「自定义角色 + 指定权限码」（幂等），返回角色主键。

    Args:
        user_id: 被授予的主体（用户主键）。
        codes: 要授予的权限码（`业务码:动作码`）。
        role_code: 角色码（按码幂等复用；必须是测试专用码，避开内置角色）。

    Returns:
        int: 角色主键。
    """
    permission_ids = await ensure_permissions(codes)
    async with shared_session(tenant_url(), read_only=False) as session:
        role = await _custom_role(session, role_code)
        if await _user_role_id(session, role_id=role.id, user_id=user_id) is None:
            session.add(SysUserRole(role_id=role.id, user_id=user_id))
        for permission_id in permission_ids.values():
            if await _role_permission_id(session, role_id=role.id, permission_id=permission_id) is None:
                session.add(
                    SysRolePermission(
                        role_id=role.id,
                        perm_type=PERM_TYPE_PERMISSION,
                        target_id=permission_id,
                    )
                )
        await session.commit()
        return int(role.id)


async def reset_permission_state(app: object) -> None:
    """清掉装配级缓存与进程级权限快照（写授权数据后、首次请求前调用）。

    Args:
        app: 已装配的应用（取 `state.cache`；无该槽位时只清进程级快照）。
    """
    cache = getattr(getattr(app, "state", None), "cache", None)
    if isinstance(cache, MemoryCacheRegion):
        cache.clear()
    reset_permission_cache_store()


async def _menu_row(session: AsyncSession) -> SysMenu:
    """取 / 建测试权限装配菜单（按路径幂等）。

    Args:
        session: 平台库会话。

    Returns:
        SysMenu: 菜单行。
    """
    row = (
        await session.execute(
            select(SysMenu)
            .where(SysMenu.path == _PERMISSION_MENU_PATH, SysMenu.deleted_at.is_(None))
            .order_by(SysMenu.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = SysMenu(
        parent_id=0,
        name=_PERMISSION_MENU_NAME,
        path=_PERMISSION_MENU_PATH,
        component=None,
        sort=9999,
        status="enabled",
    )
    session.add(row)
    await session.flush()
    return row


async def _form_id(session: AsyncSession, *, menu_id: int, business_id: int) -> int:
    """取 / 建菜单下的表单（按菜单关联幂等）。

    Args:
        session: 平台库会话。
        menu_id: 菜单主键。
        business_id: 表单挂接的业务码主键。

    Returns:
        int: 表单主键。
    """
    existing = (
        await session.execute(
            select(SysMenuForm.form_id)
            .where(SysMenuForm.menu_id == menu_id, SysMenuForm.deleted_at.is_(None))
            .order_by(SysMenuForm.form_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    form = SysForm(business_id=business_id, component=None, status="enabled")
    session.add(form)
    await session.flush()
    form_id = int(form.id)
    session.add(SysMenuForm(menu_id=menu_id, form_id=form_id))
    await session.flush()
    return form_id


async def _business_id(session: AsyncSession, code: str) -> int:
    """取 / 建业务码（按 code 幂等）。

    Args:
        session: 平台库会话。
        code: 业务码。

    Returns:
        int: 业务码主键。
    """
    existing = (
        await session.execute(
            select(SysBusiness.id)
            .where(SysBusiness.code == code, SysBusiness.deleted_at.is_(None))
            .order_by(SysBusiness.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    row = SysBusiness(code=code, name=code, status="enabled")
    session.add(row)
    await session.flush()
    return int(row.id)


async def _action_id(session: AsyncSession, code: str) -> int:
    """取 / 建动作码（按 code 幂等）。

    Args:
        session: 平台库会话。
        code: 动作码。

    Returns:
        int: 动作码主键。
    """
    existing = (
        await session.execute(
            select(SysAction.id)
            .where(SysAction.code == code, SysAction.deleted_at.is_(None))
            .order_by(SysAction.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    row = SysAction(code=code, name=code, status="enabled")
    session.add(row)
    await session.flush()
    return int(row.id)


async def _permission_id(session: AsyncSession, *, business_id: int, action_id: int) -> int:
    """取 / 建权限码（按业务码 × 动作码幂等）。

    Args:
        session: 平台库会话。
        business_id: 业务码主键。
        action_id: 动作码主键。

    Returns:
        int: 权限码主键。
    """
    existing = (
        await session.execute(
            select(SysPermission.id)
            .where(
                SysPermission.business_id == business_id,
                SysPermission.action_id == action_id,
                SysPermission.deleted_at.is_(None),
            )
            .order_by(SysPermission.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    row = SysPermission(business_id=business_id, action_id=action_id, status="enabled")
    session.add(row)
    await session.flush()
    return int(row.id)


async def _button(session: AsyncSession, *, form_id: int, permission_id: int, name: str) -> int:
    """取 / 建表单按钮（按表单 × 权限码幂等）。

    Args:
        session: 平台库会话。
        form_id: 表单主键。
        permission_id: 权限码主键。
        name: 按钮名。

    Returns:
        int: 按钮主键。
    """
    existing = (
        await session.execute(
            select(SysButton.id)
            .where(
                SysButton.form_id == form_id,
                SysButton.permission_id == permission_id,
                SysButton.deleted_at.is_(None),
            )
            .order_by(SysButton.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)
    row = SysButton(form_id=form_id, permission_id=permission_id, name=name, type="toolbar", status="enabled")
    session.add(row)
    await session.flush()
    return int(row.id)


async def _custom_role(session: AsyncSession, code: str) -> SysRole:
    """取 / 建自定义角色（按 code 幂等）。

    Args:
        session: 租户库会话。
        code: 角色码（测试专用）。

    Returns:
        SysRole: 角色行。
    """
    row = (
        await session.execute(
            select(SysRole).where(SysRole.code == code, SysRole.deleted_at.is_(None)).order_by(SysRole.id).limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = SysRole(code=code, name=code, status="enabled", role_type=ROLE_TYPE_CUSTOM)
    session.add(row)
    await session.flush()
    return row


async def _user_role_id(session: AsyncSession, *, role_id: int, user_id: int) -> int | None:
    """查用户角色绑定（无则返回 None）。

    Args:
        session: 租户库会话。
        role_id: 角色主键。
        user_id: 用户主键。

    Returns:
        int | None: 绑定行主键。
    """
    found = (
        await session.execute(
            select(SysUserRole.id)
            .where(
                SysUserRole.role_id == role_id,
                SysUserRole.user_id == user_id,
                SysUserRole.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if found is None else int(found)


async def _role_permission_id(session: AsyncSession, *, role_id: int, permission_id: int) -> int | None:
    """查角色权限码授权（无则返回 None）。

    Args:
        session: 租户库会话。
        role_id: 角色主键。
        permission_id: 权限码主键。

    Returns:
        int | None: 授权行主键。
    """
    found = (
        await session.execute(
            select(SysRolePermission.id)
            .where(
                SysRolePermission.role_id == role_id,
                SysRolePermission.perm_type == PERM_TYPE_PERMISSION,
                SysRolePermission.target_id == permission_id,
                SysRolePermission.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return None if found is None else int(found)
