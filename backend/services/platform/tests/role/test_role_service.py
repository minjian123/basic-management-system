"""角色 CRUD 与保护用例（Kiwi 2248，02_03）。

覆盖：角色码唯一（30042）/ 格式校验（10001）、内置角色禁建禁停禁删（30043）、
用户分配删除保护（30044）、乐观锁冲突、列表筛选与主体数、软删除后不可见（30041）。

注：服务写方法经 `uow.begin()` 自开事务；测试侧的读断言会使会话自动开事务，
故在每次服务调用前以 `helpers.commit` 结束当前事务（见各步骤）。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ParamError,
    RoleAssignedError,
    RoleCodeExistsError,
    RoleNotFoundError,
    RoleProtectedError,
)
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from tests.role import helpers


@pytest.mark.kiwi_id(2248)
async def test_role_crud_and_protection() -> None:
    """角色 CRUD 全链路 + 四类保护分支。"""
    target, engine = await helpers.session()
    service = helpers.role_service(target)

    role = await service.create_role(code="ops_admin", name="运维管理员")
    role_id = role.id
    role_version = role.version
    assert role.status == "enabled"

    with pytest.raises(RoleCodeExistsError) as duplicated:
        await service.create_role(code="ops_admin", name="重复")
    assert duplicated.value.code == 30042

    with pytest.raises(ParamError):
        await service.create_role(code="Bad Code", name="非法码")

    with pytest.raises(RoleProtectedError) as builtin_create:
        await service.create_role(code="system_admin", name="系统管理员")
    assert builtin_create.value.code == 30043

    created = await service.create_role(code="readonly", name="只读角色")
    created_id = created.id

    rows, total = await service.list_roles(helpers.page(), keyword="角色")
    assert total == 1 and rows[0].id == created_id
    all_rows, all_total = await service.list_roles(helpers.page(), status="enabled")
    assert all_total == 2 and len(all_rows) == 2
    await helpers.commit(target)

    detail = await service.detail(role_id)
    assert detail.version == role_version
    detail_version = detail.version
    await helpers.commit(target)

    updated = await service.update_role(role_id, name="运维负责人", status="disabled", version=detail_version)
    assert updated.name == "运维负责人" and updated.status == "disabled"

    with pytest.raises(ConcurrentConflictError):
        await service.update_role(role_id, name="过期写入", version=detail_version)

    protected = await RoleRepository(target).create(code="audit_admin", name="审计管理员")
    protected_id = protected.id
    protected_version = protected.version
    await helpers.commit(target)
    with pytest.raises(RoleProtectedError):
        await service.update_role(protected_id, status="disabled", version=protected_version)
    assert "audit_admin" in await service.protected_codes()
    await helpers.commit(target)

    with pytest.raises(RoleProtectedError):
        await service.delete_role(protected_id)

    await UserRoleRepository(target).create(role_id=role_id, user_id=1001)
    await helpers.commit(target)
    with pytest.raises(RoleAssignedError) as assigned:
        await service.delete_role(role_id)
    assert assigned.value.code == 30044

    counts = await service.subject_counts(ConcurrentStableList((role_id, created_id)))
    assert counts.get(role_id) == 1 and counts.get(created_id) == 0

    await UserRoleRepository(target).delete_by_role(role_id)
    await helpers.commit(target)
    await service.delete_role(role_id)
    with pytest.raises(RoleNotFoundError) as missing:
        await service.detail(role_id)
    assert missing.value.code == 30041

    await engine.dispose()
