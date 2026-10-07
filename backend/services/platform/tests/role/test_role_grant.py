"""角色授权用例（Kiwi 2248，02_03）。

覆盖：授权全量覆盖（先删后插 / 含来源）、来源菜单未在本次授权内（30046）、目标不存在（30046）、
条目重复（10001）、字段权限只存收窄项与「不可见即不可编辑」（10001）/ 字段不属表单（30049）、
数据权限四策略结构校验与匹配字段白名单 / 通配符越界 / 扩展未注册 / 同字典同策略重复（30047）、
授权变更后权限版本一次 +1。

注：服务写方法经 `uow.begin()` 自开事务；测试侧读断言会使会话自动开事务，
故在每次服务调用前以 `helpers.commit` 结束当前事务。
"""

import pytest

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ParamError,
    RoleFieldMismatchError,
    RoleNotFoundError,
    RoleScopeValueInvalidError,
    RoleTargetInvalidError,
)
from bms_core.permission.version import permission_version_key
from bms_platform.models.role import NO_SOURCE_MENU_ID, PERM_TYPE_ACTION, PERM_TYPE_FORM, PERM_TYPE_MENU
from bms_platform.repositories.role import RoleRepository
from bms_platform.services.role_grant import DataScopeGrantEntry, FieldGrantEntry, PermissionGrantEntry
from tests.role import helpers

_TENANT = "1001"
_NO_SOURCE = NO_SOURCE_MENU_ID


def _entries(*items: tuple[str, int, int]) -> ConcurrentStableList[PermissionGrantEntry]:
    """构造授权条目清单。

    Args:
        *items: (授权类型, 目标 ID, 来源菜单 ID)。

    Returns:
        ConcurrentStableList[PermissionGrantEntry]: 授权条目清单。
    """
    return ConcurrentStableList(PermissionGrantEntry(perm_type=t, target_id=i, source_menu_id=s) for t, i, s in items)


def _items(*items: dict[str, object]) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """构造策略配置清单。

    Args:
        *items: 配置项映射。

    Returns:
        ConcurrentStableList[ConcurrentStableDict[str, object]]: 策略配置清单。
    """
    return ConcurrentStableList(ConcurrentStableDict(item) for item in items)


@pytest.mark.kiwi_id(2248)
async def test_permissions_full_replace_and_source_validation() -> None:
    """菜单 / 表单 / 操作授权全量覆盖、来源校验与目标校验；版本一次 +1。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    role_id = role.id
    menu_id, _business_id, form_id, action_id = await helpers.seed_metadata(target)
    cache = MemoryCacheRegion()
    service = helpers.grant_service(target, cache)

    created = await service.replace_permissions(
        role_id,
        _entries(
            (PERM_TYPE_MENU, menu_id, _NO_SOURCE),
            (PERM_TYPE_FORM, form_id, menu_id),
            (PERM_TYPE_ACTION, action_id, menu_id),
        ),
        tenant_id=_TENANT,
    )
    assert {(row.perm_type, row.target_id, row.source_menu_id) for row in created} == {
        (PERM_TYPE_MENU, menu_id, _NO_SOURCE),
        (PERM_TYPE_FORM, form_id, menu_id),
        (PERM_TYPE_ACTION, action_id, menu_id),
    }
    assert cache.get(permission_version_key(_TENANT)) == 1

    # 全量覆盖：仅保留本次条目
    await service.replace_permissions(role_id, _entries((PERM_TYPE_MENU, menu_id, _NO_SOURCE)), tenant_id=_TENANT)
    remaining = await service.list_permission_entries(role_id)
    assert [(row.perm_type, row.target_id) for row in remaining] == [(PERM_TYPE_MENU, menu_id)]
    assert cache.get(permission_version_key(_TENANT)) == 2
    await helpers.commit(target)

    with pytest.raises(RoleTargetInvalidError) as source_missing:
        await service.replace_permissions(role_id, _entries((PERM_TYPE_FORM, form_id, menu_id)), tenant_id=_TENANT)
    assert source_missing.value.code == 30046

    with pytest.raises(RoleTargetInvalidError):
        await service.replace_permissions(
            role_id, _entries((PERM_TYPE_ACTION, 999999999, _NO_SOURCE)), tenant_id=_TENANT
        )

    with pytest.raises(ParamError):
        await service.replace_permissions(
            role_id,
            _entries((PERM_TYPE_MENU, menu_id, _NO_SOURCE), (PERM_TYPE_MENU, menu_id, _NO_SOURCE)),
            tenant_id=_TENANT,
        )

    with pytest.raises(ParamError):
        await service.replace_permissions(role_id, _entries(("unknown", menu_id, _NO_SOURCE)), tenant_id=_TENANT)

    # 失败整体回滚：版本与授权行保持覆盖前状态
    assert cache.get(permission_version_key(_TENANT)) == 2
    after = await service.list_permission_entries(role_id)
    assert len(after) == 1
    await helpers.commit(target)

    with pytest.raises(RoleNotFoundError):
        await service.list_permission_entries(999999999)

    await engine.dispose()


@pytest.mark.kiwi_id(2248)
async def test_fields_narrowing_and_form_mismatch() -> None:
    """字段权限只存收窄项、不可见即不可编辑（10001）、字段不属表单（30049）。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    role_id = role.id
    _menu_id, _business_id, form_id, _action_id = await helpers.seed_metadata(target)
    field_id = await helpers.seed_form_field(target, form_id)
    cache = MemoryCacheRegion()
    service = helpers.grant_service(target, cache)

    created = await service.replace_fields(
        role_id,
        ConcurrentStableList((FieldGrantEntry(form_id=form_id, field_id=field_id, visible=True, editable=False),)),
        tenant_id=_TENANT,
    )
    assert len(created) == 1 and created[0].editable is False
    assert cache.get(permission_version_key(_TENANT)) == 1

    with pytest.raises(ParamError):
        await service.replace_fields(
            role_id,
            ConcurrentStableList((FieldGrantEntry(form_id=form_id, field_id=field_id, visible=False, editable=True),)),
            tenant_id=_TENANT,
        )

    with pytest.raises(RoleFieldMismatchError) as mismatch:
        await service.replace_fields(
            role_id,
            ConcurrentStableList((FieldGrantEntry(form_id=form_id, field_id=999999999),)),
            tenant_id=_TENANT,
        )
    assert mismatch.value.code == 30049

    assert cache.get(permission_version_key(_TENANT)) == 1
    kept = await service.list_field_entries(role_id)
    assert len(kept) == 1
    await engine.dispose()


@pytest.mark.kiwi_id(2248)
async def test_data_scopes_policy_validation_and_whitelist() -> None:
    """数据权限：选择 / 区域 / 匹配三策略落库；白名单 / 通配符 / 扩展注册 / 去重与字典存在性校验。"""
    target, engine = await helpers.session()
    role = await RoleRepository(target).create(code="ops", name="运维角色")
    role_id = role.id
    dict_type_id, attr_key = await helpers.seed_dict(target)
    cache = MemoryCacheRegion()
    service = helpers.grant_service(target, cache)

    created = await service.replace_data_scopes(
        role_id,
        ConcurrentStableList(
            (
                DataScopeGrantEntry(
                    dict_type_id=dict_type_id, policy_type="select", config=_items({"item_code": "enabled"})
                ),
                DataScopeGrantEntry(
                    dict_type_id=dict_type_id, policy_type="region", config=_items({"start": "a", "end": "m"})
                ),
                DataScopeGrantEntry(
                    dict_type_id=dict_type_id,
                    policy_type="match",
                    config=_items({"field": "code", "pattern": "user_*"}, {"field": attr_key, "pattern": "A?"}),
                ),
            )
        ),
        tenant_id=_TENANT,
    )
    assert {row.policy_type for row in created} == {"select", "region", "match"}
    assert cache.get(permission_version_key(_TENANT)) == 1
    await helpers.commit(target)

    with pytest.raises(RoleScopeValueInvalidError) as bad_field:
        await service.replace_data_scopes(
            role_id,
            ConcurrentStableList(
                (
                    DataScopeGrantEntry(
                        dict_type_id=dict_type_id,
                        policy_type="match",
                        config=_items({"field": "disabled_key", "pattern": "a"}),
                    ),
                )
            ),
            tenant_id=_TENANT,
        )
    assert bad_field.value.code == 30047

    with pytest.raises(RoleScopeValueInvalidError):
        await service.replace_data_scopes(
            role_id,
            ConcurrentStableList(
                (
                    DataScopeGrantEntry(
                        dict_type_id=dict_type_id,
                        policy_type="match",
                        config=_items({"field": "code", "pattern": "a[b]"}),
                    ),
                )
            ),
            tenant_id=_TENANT,
        )

    with pytest.raises(RoleScopeValueInvalidError):
        await service.replace_data_scopes(
            role_id,
            ConcurrentStableList(
                (
                    DataScopeGrantEntry(
                        dict_type_id=dict_type_id, policy_type="extension", config=_items({"key": "dept_subtree"})
                    ),
                )
            ),
            tenant_id=_TENANT,
        )

    with pytest.raises(RoleScopeValueInvalidError):
        await service.replace_data_scopes(
            role_id,
            ConcurrentStableList(
                (
                    DataScopeGrantEntry(
                        dict_type_id=dict_type_id, policy_type="select", config=_items({"item_code": "enabled"})
                    ),
                    DataScopeGrantEntry(
                        dict_type_id=dict_type_id, policy_type="select", config=_items({"item_code": "disabled"})
                    ),
                )
            ),
            tenant_id=_TENANT,
        )

    with pytest.raises(RoleScopeValueInvalidError):
        await service.replace_data_scopes(
            role_id,
            ConcurrentStableList(
                (DataScopeGrantEntry(dict_type_id=999999999, policy_type="select", config=_items({"a": 1})),)
            ),
            tenant_id=_TENANT,
        )

    assert cache.get(permission_version_key(_TENANT)) == 1
    kept = await service.list_data_scope_entries(role_id)
    assert len(kept) == 3
    await engine.dispose()
