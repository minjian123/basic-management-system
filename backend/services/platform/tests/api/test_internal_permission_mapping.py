"""平台权限内部契约映射用例（`04_01`）：基座中性数据 → 内部契约响应。

两条只读出口（`subject` / `metadata`）的响应体由 `_to_subject_result` / `_to_metadata_result`
从基座契约转换而来；本文件覆盖**非空数据**的逐字段映射与空数据的兜底（键保留、集合为空）。
"""

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.permission.field import FieldPermission
from bms_core.permission.sources import (
    DataScopeRule,
    PermissionGrant,
    PermissionMetadata,
    PermissionSubjectData,
)
from bms_platform.api import permission as permission_api

_to_metadata_result = permission_api._to_metadata_result  # pyright: ignore[reportPrivateUsage]
_to_subject_result = permission_api._to_subject_result  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2320)
def test_subject_result_maps_all_fields() -> None:
    """映射：角色 / 类型 / 授权 / 数据范围 / 字段收窄逐项转换（主键字符串化）。"""
    config: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    row: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    row.set("field", "area_code")
    config.add(row)
    data = PermissionSubjectData(role_ids=ConcurrentStableSet([11, 12]))
    data.role_types.set(11, "custom")
    data.role_types.set(12, "system")
    data.grants.add(PermissionGrant(perm_type="menu", target_id=900))
    data.grants.add(PermissionGrant(perm_type="permission", target_id=902))
    data.data_scope_rules.add(DataScopeRule(data_source_key="role", policy_type="select", config=config))
    data.field_perms.add(FieldPermission(form_id=901, field_key="salary", visible=False, editable=False))

    result = _to_subject_result(data)
    assert list(result.role_ids) == [11, 12]
    assert result.role_types.get("11") == "custom"
    assert result.role_types.get("12") == "system"
    assert [(item.perm_type, item.target_id) for item in result.grants] == [
        ("menu", 900),
        ("permission", 902),
    ]
    assert len(result.data_scope_rules) == 1
    rule = result.data_scope_rules[0]
    assert rule.data_source_key == "role"
    assert rule.policy_type == "select"
    assert [dict(item) for item in rule.config] == [{"field": "area_code"}]
    assert len(result.field_perms) == 1
    perm = result.field_perms[0]
    assert (perm.form_id, perm.field_key, perm.visible, perm.editable) == (901, "salary", False, False)


@pytest.mark.kiwi_id(2320)
def test_subject_result_maps_empty_data() -> None:
    """映射兜底：空数据 → 各集合为空（无角色 / 无授权 / 无规则 / 无字段收窄）。"""
    result = _to_subject_result(PermissionSubjectData())
    assert list(result.role_ids) == []
    assert list(result.role_types) == []
    assert list(result.grants) == []
    assert list(result.data_scope_rules) == []
    assert list(result.field_perms) == []


@pytest.mark.kiwi_id(2320)
def test_subject_result_skips_role_without_type() -> None:
    """映射容错：角色无类型记录时跳过（不写空类型）。"""
    data = PermissionSubjectData(role_ids=ConcurrentStableSet([11]))
    result = _to_subject_result(data)
    assert list(result.role_ids) == [11]
    assert list(result.role_types) == []


@pytest.mark.kiwi_id(2320)
def test_metadata_result_maps_all_fields() -> None:
    """映射：菜单 → 表单（主键字符串化）、权限码 id → 权限码、版本透传。"""
    metadata = PermissionMetadata(version=7)
    metadata.menu_forms.set(900, ConcurrentStableList([901, 999]))
    metadata.permission_codes.set(902, "employee:query")

    result = _to_metadata_result(metadata)
    assert result.version == 7
    assert list(result.menu_forms.get("900") or []) == [901, 999]
    assert result.permission_codes.get("902") == "employee:query"


@pytest.mark.kiwi_id(2320)
def test_metadata_result_maps_empty_data() -> None:
    """映射兜底：空元数据 → 版本 0、两索引为空。"""
    result = _to_metadata_result(PermissionMetadata())
    assert result.version == 0
    assert list(result.menu_forms) == []
    assert list(result.permission_codes) == []
