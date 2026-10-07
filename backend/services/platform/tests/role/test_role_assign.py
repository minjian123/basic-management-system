"""角色分配（角色 × 用户）用例（Kiwi 2248，02_03）。

覆盖：批量分配幂等 upsert（已分配跳过 / 历史软删行**恢复原行**）、解绑软删与幂等无操作、
用户不存在 / 停用（30045）、已分配列表（同库取用户属性 + 关键字 / 状态筛选）、
分配与解绑后权限版本递增。

注：服务写方法经 `uow.begin()` 自开事务；测试侧读断言会使会话自动开事务，
故在每次服务调用前以 `helpers.commit` 结束当前事务。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import RoleNotFoundError, RoleSubjectInvalidError
from bms_core.permission.version import permission_version_key
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from tests.role import helpers

_TENANT = "1001"


async def _seed(target: AsyncSession) -> tuple[int, int, int, int]:
    """播种一个角色与三个用户（一名停用）。

    Args:
        target: 会话。

    Returns:
        tuple[int, int, int, int]: (角色 ID, 用户 A, 用户 B, 停用用户 C)。
    """
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    users = UserRepository(target)
    user_a = await users.create(username="alice", password_hash="x", name="爱丽丝")
    user_b = await users.create(username="bob", password_hash="x", name="鲍勃")
    user_c = await users.create(username="carol", password_hash="x", name="卡罗", status="disabled")
    await target.commit()
    return role.id, user_a.id, user_b.id, user_c.id


@pytest.mark.kiwi_id(2248)
async def test_assign_is_idempotent_and_restores_unassigned_rows() -> None:
    """分配幂等（重复分配不新增）、解绑软删、再次分配恢复原行；版本递增。"""
    target, engine = await helpers.session()
    role_id, user_a, user_b, _ = await _seed(target)
    cache = MemoryCacheRegion()
    service = helpers.assign_service(target, cache)

    assigned = await service.assign_users(role_id, ConcurrentStableList((user_a, user_b)), tenant_id=_TENANT)
    assert [user.id for user in assigned] == [user_a, user_b]

    await service.assign_users(role_id, ConcurrentStableList((user_a,)), tenant_id=_TENANT)
    rows = await UserRoleRepository(target).list_by_role(role_id)
    assert len(rows) == 2
    await helpers.commit(target)

    assert await service.unassign_user(role_id, user_a, tenant_id=_TENANT) is True
    assert await service.unassign_user(role_id, user_a, tenant_id=_TENANT) is False
    remaining = await UserRoleRepository(target).list_by_role(role_id)
    assert [row.user_id for row in remaining] == [user_b]
    await helpers.commit(target)

    await service.assign_users(role_id, ConcurrentStableList((user_a,)), tenant_id=_TENANT)
    restored = await UserRoleRepository(target).list_by_role(role_id)
    assert len(restored) == 2 and len({row.id for row in restored}) == 2
    await helpers.commit(target)

    # 一次分配 + 一次解绑 + 一次恢复 = 3 次递增（重复分配与重复解绑不递增）
    version = cache.get(permission_version_key(_TENANT))
    assert isinstance(version, int) and version == 3
    await engine.dispose()


@pytest.mark.kiwi_id(2248)
async def test_assign_rejects_invalid_subject_and_lists_with_filters() -> None:
    """用户不存在 / 停用 → 30045；已分配列表按账号 / 姓名与状态筛选；角色不存在 → 30041。"""
    target, engine = await helpers.session()
    role_id, user_a, user_b, user_c = await _seed(target)
    service = helpers.assign_service(target)

    with pytest.raises(RoleSubjectInvalidError) as disabled:
        await service.assign_users(role_id, ConcurrentStableList((user_c,)), tenant_id=_TENANT)
    assert disabled.value.code == 30045

    with pytest.raises(RoleSubjectInvalidError):
        await service.assign_users(role_id, ConcurrentStableList((999999999,)), tenant_id=_TENANT)

    rows = await UserRoleRepository(target).list_by_role(role_id)
    assert len(rows) == 0
    await helpers.commit(target)

    await service.assign_users(role_id, ConcurrentStableList((user_a, user_b)), tenant_id=_TENANT)
    by_keyword, keyword_total = await service.list_assigned(role_id, helpers.page(), keyword="ali")
    assert keyword_total == 1 and by_keyword[0].id == user_a

    by_name, name_total = await service.list_assigned(role_id, helpers.page(), keyword="鲍")
    assert name_total == 1 and by_name[0].id == user_b

    disabled_rows, disabled_total = await service.list_assigned(role_id, helpers.page(), status="disabled")
    assert disabled_total == 0 and len(disabled_rows) == 0

    with pytest.raises(RoleNotFoundError):
        await service.list_assigned(999999999, helpers.page())
    await helpers.commit(target)

    with pytest.raises(RoleNotFoundError):
        await service.unassign_user(999999999, user_a, tenant_id=_TENANT)

    await engine.dispose()
