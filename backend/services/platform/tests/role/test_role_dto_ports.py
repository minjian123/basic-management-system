"""角色域 DTO 与领域服务接口用例（07C `03_04`）。

覆盖：`dto.py` 的 `from_model` 字段映射（角色 / 授权 / 字段权限 / 数据范围）、`ports.py` 各读面
实现的取数、`set_user_roles` 的全量覆盖写（含无守卫与守卫拒绝两态）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import UserSeparationConflictError
from bms_core.models.platform.role import (
    ROLE_TYPE_CUSTOM,
    ROLE_TYPE_SYSTEM,
    SysDataScope,
    SysRole,
    SysRoleField,
    SysRolePermission,
)
from bms_platform.domains.role.dto import (
    RoleDataScopeEntry,
    RoleDetail,
    RoleFieldGrant,
    RolePermissionEntry,
    RoleSummary,
)
from bms_platform.domains.role.services.role_assignment import RoleAssignmentService
from bms_platform.domains.role.services.role_grant_reader import RoleGrantReader
from bms_platform.domains.role.services.role_query import RoleQueryService
from bms_platform.domains.role.services.role_reference import RoleReferenceService
from tests.role import helpers

_NOW = datetime.now(UTC).replace(tzinfo=None)


def _role(*, role_id: int = 7, code: str = "ops", role_type: str = ROLE_TYPE_SYSTEM) -> SysRole:
    """造角色记录（不落库）。

    Args:
        role_id: 主键。
        code: 角色码。
        role_type: 角色类型。

    Returns:
        SysRole: 角色记录。
    """
    return SysRole(
        id=role_id,
        form_key="role",
        code=code,
        name="运维",
        status="enabled",
        role_type=role_type,
        created_at=_NOW,
        updated_at=_NOW,
        version=3,
        created_by=1,
        updated_by=2,
    )


def test_role_dto_from_model() -> None:
    """DTO 映射：角色摘要 / 详情 / 授权 / 字段权限 / 数据范围字段逐一对应。"""
    row = _role()
    summary = RoleSummary.from_model(row)
    assert (summary.id, summary.code, summary.name, summary.status) == (7, "ops", "运维", "enabled")
    assert summary.role_type == ROLE_TYPE_SYSTEM
    assert summary.builtin is True
    assert RoleSummary.from_model(_role(role_type=ROLE_TYPE_CUSTOM)).builtin is False

    detail = RoleDetail.from_model(row)
    assert (detail.version, detail.created_by, detail.updated_by) == (3, 1, 2)
    assert detail.created_at == _NOW and detail.updated_at == _NOW

    grant = RolePermissionEntry.from_model(
        SysRolePermission(id=11, role_id=7, perm_type="menu", target_id=21, source_menu_id=0)
    )
    assert (grant.perm_type, grant.target_id, grant.source_menu_id) == ("menu", 21, 0)

    field_grant = RoleFieldGrant.from_model(
        SysRoleField(id=12, role_id=7, form_id=31, field_id=41, visible=True, editable=False, source_menu_id=0)
    )
    assert (field_grant.form_id, field_grant.field_id) == (31, 41)
    assert (field_grant.visible, field_grant.editable) == (True, False)

    config: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    config.add(ConcurrentStableDict({"values": ["13"]}))
    scope = RoleDataScopeEntry.from_model(
        SysDataScope(id=13, role_id=7, data_source_key="org_dept", policy_type="select", config=config)
    )
    assert (scope.data_source_key, scope.policy_type) == ("org_dept", "select")
    assert cast("Any", scope.config)[0].get("values") == ["13"]


async def test_role_ports_read_paths() -> None:
    """端口读面：查询 / 引用 / 授权读面各自取数，空集合返回空清单。"""
    session, engine = await helpers.session()
    try:
        role = _role()
        session.add(role)
        await session.commit()

        query = RoleQueryService(cast("Any", session))
        assert (await query.get(role.id)) is not None
        assert (await query.get(999)) is None
        assert [item.code for item in await query.list_by_ids(ConcurrentStableList([role.id]))] == ["ops"]
        found = await query.list_by_code("ops")
        assert found is not None and found.name == "运维"
        assert (await query.list_by_code("missing")) is None

        reference = RoleReferenceService(cast("Any", session))
        assert [item.id for item in await reference.list_options()] == [role.id]

        grants = RoleGrantReader(cast("Any", session))
        types = await grants.list_role_types(ConcurrentStableList([role.id]))
        assert types[role.id] == ROLE_TYPE_SYSTEM
        assert await grants.list_permission_grants(ConcurrentStableList([role.id])) == []
        assert await grants.list_data_scopes(ConcurrentStableList([role.id])) == []
    finally:
        await engine.dispose()


async def test_role_assignment_port_writes_and_guard() -> None:
    """分配端口：读绑定 / 全量覆盖写 / 守卫拒绝 / 角色缺失。"""
    session, engine = await helpers.session()
    try:
        role = _role()
        other = _role(role_id=8, code="audit")
        session.add_all([role, other])
        await session.commit()

        service = RoleAssignmentService(cast("Any", session))
        assert await service.list_role_ids_of_user(1) == []
        assert await service.list_roles_of_user(1) == []
        assert await service.count_by_user(1) == 0

        applied = await service.set_user_roles(1, ConcurrentStableList([role.id, role.id]))
        assert [item.code for item in applied] == ["ops"]
        await helpers.commit(cast("Any", session))
        assert list(await service.list_role_ids_of_user(1)) == [role.id]
        assert await service.count_by_user(1) == 1

        await service.set_user_roles(1, ConcurrentStableList([other.id]))
        await helpers.commit(cast("Any", session))
        assert list(await service.list_role_ids_of_user(1)) == [other.id]

        with pytest.raises(Exception, match="角色不存在"):
            await service.set_user_roles(1, ConcurrentStableList([987654]))

        class _Guard:
            """守卫替身：直接拒绝（验证 set_user_roles 在写前调用守卫）。"""

            async def ensure_user_roles_exclusive(
                self, *, user_ids: ConcurrentStableList[int], roles: ConcurrentStableList[RoleSummary]
            ) -> None:
                """始终拒绝。

                Args:
                    user_ids: 用户主键。
                    roles: 目标角色。

                Raises:
                    UserSeparationConflictError: 恒定。
                """
                del user_ids, roles
                raise UserSeparationConflictError("互斥")

        guarded = RoleAssignmentService(cast("Any", session), guard=cast("Any", _Guard()))
        with pytest.raises(UserSeparationConflictError):
            await guarded.set_user_roles(1, ConcurrentStableList([other.id]))
    finally:
        await engine.dispose()
