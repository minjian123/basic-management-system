"""平台仓储路径补齐用例（`02_03` / `02_04`）：角色域与菜单域仓储未覆盖分支。

补齐 `repositories/role.py` 与 `repositories/menu.py` 既有用例未触达的路径：空集合短路、
按用户 / 角色列举与软删、分配行筛选（用户属性子查询）、恢复未命中，以及菜单 / 业务 /
动作多语言装载与菜单 × 表单关联读取 / 按菜单软删。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    FormRepository,
    MenuFormRepository,
    MenuRepository,
)
from bms_platform.repositories.role import (
    DataScopeRepository,
    RoleFieldRepository,
    RolePermissionRepository,
    RoleRepository,
    UserRoleRepository,
)
from bms_platform.repositories.user import UserRepository
from tests.role import helpers


async def test_role_repository_empty_lookup_and_assignment_paths() -> None:
    """角色域仓储：空集合短路、按用户列举、保留集合外软删与恢复未命中。"""
    target, engine = await helpers.session()
    roles = RoleRepository(target)
    assignments = UserRoleRepository(target)

    assert list(await roles.list_by_ids(ConcurrentStableSet())) == []

    role_one = await roles.create(code="r1", name="角色一")
    role_two = await roles.create(code="r2", name="角色二")
    user_a = (await UserRepository(target).create(username="alice", password_hash="h", name="爱丽丝")).id
    user_b = (await UserRepository(target).create(username="bob", password_hash="h", name="鲍勃")).id
    await assignments.create(role_id=role_one.id, user_id=user_a)
    await assignments.create(role_id=role_two.id, user_id=user_a)
    await assignments.create(role_id=role_one.id, user_id=user_b)
    await target.commit()

    assert list(await assignments.list_user_ids_by_role(role_one.id)) == [user_a, user_b]
    assert list(await assignments.list_user_ids_by_role(role_two.id)) == [user_a]
    assert [row.role_id for row in await assignments.list_by_user(user_a)] == [role_one.id, role_two.id]

    # 按用户保留集合外软删：user_a 在「角色二」的分配行被软删。
    await assignments.soft_delete_by_user_except(user_a, ConcurrentStableSet([role_one.id]))
    await target.commit()
    assert list(await assignments.list_user_ids_by_role(role_two.id)) == []

    # 按角色保留集合外软删：user_b 在「角色一」的分配行被软删。
    await assignments.soft_delete_by_role_except(role_one.id, ConcurrentStableSet([user_a]))
    await target.commit()
    assert list(await assignments.list_user_ids_by_role(role_one.id)) == [user_a]

    assert await assignments.restore(999999) is False
    await engine.dispose()


async def test_role_repository_assignment_filters_by_user_attributes() -> None:
    """分配行筛选：用户账号 / 姓名经同库子查询过滤（含状态）。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="r2", name="角色二")
    user_a = (await UserRepository(target).create(username="alice", password_hash="h", name="爱丽丝")).id
    disabled = (
        await UserRepository(target).create(username="bob", password_hash="h", name="鲍勃", status="disabled")
    ).id
    assignments = UserRoleRepository(target)
    await assignments.create(role_id=role.id, user_id=user_a)
    await assignments.create(role_id=role.id, user_id=disabled)
    await target.commit()

    rows = await assignments.list_filtered_by_role(role.id, helpers.page(), keyword="alice", status="enabled")
    assert [row.user_id for row in rows] == [user_a]
    assert await assignments.count_filtered_by_role(role.id, keyword="alice", status="enabled") == 1
    await engine.dispose()


async def test_role_repository_empty_keep_and_unfiltered_paths() -> None:
    """角色域仓储：空保留集合（全量软删）与无筛选条件的列举 / 计数。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="r3", name="角色三")
    user_a = (await UserRepository(target).create(username="alice", password_hash="h", name="爱丽丝")).id
    assignments = UserRoleRepository(target)
    await assignments.create(role_id=role.id, user_id=user_a)
    await target.commit()

    # 空保留集合：条件分支短路，软删全部生效行。
    await assignments.soft_delete_by_user_except(user_a, ConcurrentStableSet())
    await target.commit()
    assert list(await assignments.list_user_ids_by_role(role.id)) == []

    await assignments.soft_delete_by_role_except(role.id, ConcurrentStableSet())

    # 无筛选条件：用户属性子查询整段短路。
    assert await assignments.count_filtered_by_role(role.id) == 0
    assert list(await assignments.list_filtered_by_role(role.id, helpers.page())) == []
    await engine.dispose()


async def test_multi_role_repository_empty_lists() -> None:
    """授权 / 字段 / 数据权限仓储：空角色集合短路返回空清单。"""
    target, engine = await helpers.session()
    assert list(await RolePermissionRepository(target).list_by_roles(ConcurrentStableSet())) == []
    assert list(await RoleFieldRepository(target).list_by_roles(ConcurrentStableSet())) == []
    assert list(await DataScopeRepository(target).list_by_roles(ConcurrentStableSet())) == []
    await engine.dispose()


async def test_menu_repository_i18n_and_association_paths() -> None:
    """菜单域仓储：业务 / 动作多语言装载、菜单 × 表单关联读取与按菜单软删。"""
    target, engine = await helpers.session()
    menu = await MenuRepository(target).create(
        parent_id=0, name="页面", path="/p", component=None, icon=None, sort=1, hidden=False, status="enabled"
    )
    business = await BusinessRepository(target).create(code="b1", name="业务", status="enabled")
    action = await ActionRepository(target).create(code="create", name="新建", status="enabled")
    form = await FormRepository(target).create(business_id=business.id, component=None, status="enabled")
    links = MenuFormRepository(target)
    await links.create(menu_id=menu.id, form_id=form.id)
    await target.commit()

    assert len(await BusinessRepository(target).list_i18n(ConcurrentStableList([business.id]), "zh-CN")) == 0
    assert len(await ActionRepository(target).list_i18n(ConcurrentStableList([action.id]), "zh-CN")) == 0
    assert list(await links.list_form_ids_by_menu(menu.id)) == [form.id]
    assert (await links.get_by_menu_form(menu.id, form.id)) is not None

    await links.delete_by_menu(menu.id)
    await target.commit()
    assert (await links.get_by_menu_form(menu.id, form.id)) is None
    await engine.dispose()
