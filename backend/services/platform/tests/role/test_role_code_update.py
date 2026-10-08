"""角色码可改用例（Kiwi 2267，02_03 追加子任务「角色码可改与内置判定脱钩」）。

覆盖：角色码可改（成功 / 与他角色重复 `30042` / 格式非法 `10001` / 自身同值幂等）、
内置角色（`role_type != custom`）可改角色码且保护不因此解除、新建角色类型恒为 `custom`。

注：服务写方法经 `uow.begin()` 自开事务；测试侧读断言会使会话自动开事务，
故在每次服务调用前以 `helpers.commit` 结束当前事务（同 `test_role_service.py` 口径）。
"""

import pytest

from bms_core.core.exceptions import ParamError, RoleCodeExistsError, RoleProtectedError
from bms_platform.repositories.role import RoleRepository
from tests.role import helpers


@pytest.mark.kiwi_id(2267)
async def test_update_role_code() -> None:
    """角色码可改：成功 / 重复 / 格式非法 / 自身同值豁免；新建类型恒为自定义。"""
    target, engine = await helpers.session()
    service = helpers.role_service(target)

    role = await service.create_role(code="ops_admin", name="运维管理员")
    role_id = role.id
    version = role.version
    assert role.role_type == "custom"
    await service.create_role(code="dev_admin", name="研发管理员")
    await helpers.commit(target)

    updated = await service.update_role(role_id, code="ops_admin_v2", version=version)
    assert updated.code == "ops_admin_v2"
    version = updated.version
    await helpers.commit(target)

    with pytest.raises(RoleCodeExistsError) as duplicated:
        await service.update_role(role_id, code="dev_admin", version=version)
    assert duplicated.value.code == 30042

    with pytest.raises(ParamError):
        await service.update_role(role_id, code="Bad Code", version=version)

    same = await service.update_role(role_id, code="ops_admin_v2", version=version)
    assert same.code == "ops_admin_v2"
    await helpers.commit(target)

    await engine.dispose()


@pytest.mark.kiwi_id(2267)
async def test_builtin_role_code_update_keeps_protection() -> None:
    """内置角色可改角色码（改码不解除内置保护：仍禁停用 / 禁删除）。"""
    target, engine = await helpers.session()
    service = helpers.role_service(target)

    role = await RoleRepository(target).create(code="audit_admin", name="审计管理员", role_type="audit")
    role_id = role.id
    version = role.version
    await helpers.commit(target)

    renamed = await service.update_role(role_id, code="audit_admin_v2", version=version)
    assert renamed.code == "audit_admin_v2"
    version = renamed.version
    await helpers.commit(target)

    with pytest.raises(RoleProtectedError):
        await service.update_role(role_id, status="disabled", version=version)
    await helpers.commit(target)

    with pytest.raises(RoleProtectedError):
        await service.delete_role(role_id)

    await engine.dispose()
