"""用户权限快照载荷容错用例（`permission/snapshot.py`）：集合类载荷分支与缺字段回落。

补齐 `_as_list` 对 `ConcurrentStableList` 载荷的处理分支与 `_as_stable` 空值回落分支；
`from_payload` 缺字段 / 类型异常一律回落默认（不抛错）。
"""

from __future__ import annotations

import json

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import PermissionError
from bms_core.permission.field import FieldPermission
from bms_core.permission.profile import DEFAULT_PROFILE
from bms_core.permission.snapshot import (
    TIER_STANDARD,
    TIER_SYSTEM_ADMIN,
    PermissionSnapshot,
    assert_fields_writable,
    get_current_permission_snapshot,
    set_current_permission_snapshot,
)


def _payload_from_json(text: str) -> ConcurrentStableDict[str, object]:
    """以 JSON 解析构造载荷（与缓存读回同形态）。

    Args:
        text: JSON 文本。

    Returns:
        ConcurrentStableDict[str, object]: 载荷。
    """
    return ConcurrentStableDict(json.loads(text))


@pytest.mark.kiwi_id(2269)
def test_from_payload_accepts_stable_list_payload() -> None:
    """载荷值为 `ConcurrentStableList` 时按保序列表规整（集合类载荷分支）。"""
    snapshot = PermissionSnapshot.from_payload(
        ConcurrentStableDict(
            {
                "permission_codes": ConcurrentStableList(["role:grant", 7]),
                "granted_menu_ids": ConcurrentStableList([1, "x", True]),
                "granted_form_ids": ConcurrentStableList([2, 3]),
                "data_scopes": ConcurrentStableList([ConcurrentStableDict({"policy_type": "all"})]),
                "field_perms": ConcurrentStableList([ConcurrentStableDict({"form_id": 5, "field_key": "name"})]),
            }
        )
    )
    assert snapshot.permission_codes == ConcurrentStableSet({"role:grant"})
    assert snapshot.granted_menu_ids == ConcurrentStableSet({1})
    assert snapshot.granted_form_ids == ConcurrentStableSet({2, 3})
    assert list(snapshot.data_scopes) == [{"policy_type": "all"}]
    assert snapshot.field_state(5, "name") == (True, True)


@pytest.mark.kiwi_id(2269)
def test_from_payload_falls_back_on_bad_types() -> None:
    """缺字段 / 类型异常回落默认（版本 0 / 档位缺省 / 层级 standard / 扩展空映射）。"""
    snapshot = PermissionSnapshot.from_payload(
        _payload_from_json('{"version": true, "profile": 5, "tier": null, "extensions": "x"}')
    )
    assert snapshot.version == 0
    assert snapshot.profile == DEFAULT_PROFILE
    assert snapshot.tier == TIER_STANDARD
    assert snapshot.extensions == ConcurrentStableDict()
    assert snapshot.permission_codes == ConcurrentStableSet()


@pytest.mark.kiwi_id(2269)
def test_from_payload_ignores_non_mapping_payload() -> None:
    """非映射载荷（标量 / 列表）整体回落空快照（不抛错）。"""
    for payload in (None, "x", 7, ConcurrentStableList([1, 2])):
        snapshot = PermissionSnapshot.from_payload(payload)
        assert snapshot.permission_codes == ConcurrentStableSet()
        assert snapshot.data_scopes == ConcurrentStableList()


@pytest.mark.kiwi_id(2269)
def test_payload_roundtrip_and_field_state() -> None:
    """`to_payload` / `from_payload` 往返保真（码集 / 菜单 / 表单 / 范围 / 字段收窄）。"""
    original = PermissionSnapshot(
        version=3,
        profile=DEFAULT_PROFILE,
        tier=TIER_STANDARD,
        permission_codes=ConcurrentStableSet({"role:grant"}),
        granted_menu_ids=ConcurrentStableSet({11}),
        granted_form_ids=ConcurrentStableSet({22}),
        data_scopes=ConcurrentStableList([ConcurrentStableDict({"policy_type": "self"})]),
        field_perms=ConcurrentStableList(
            [FieldPermission(form_id=1, field_key="secret", visible=False, editable=False)]
        ),
        extensions=ConcurrentStableDict({"extra": 1}),
    )
    restored = PermissionSnapshot.from_payload(original.to_payload())

    assert restored == original
    assert restored.holds("role:grant") is True
    assert restored.holds("role:delete") is False
    assert restored.field_state(1, "secret") == (False, False)
    assert restored.field_state(1, "open") is None


@pytest.mark.kiwi_id(2269)
def test_assert_fields_writable_paths() -> None:
    """写时字段校验：无快照放行；豁免层级放行；含不可编辑字段即拒。"""
    set_current_permission_snapshot(None)
    assert get_current_permission_snapshot() is None
    assert_fields_writable(form_id=1, values=ConcurrentStableDict({"secret": "x"}))

    exempt = PermissionSnapshot(tier=TIER_SYSTEM_ADMIN)
    set_current_permission_snapshot(exempt)
    assert_fields_writable(form_id=1, values=ConcurrentStableDict({"secret": "x"}))

    # 普通层级：收窄项不命中目标字段 ⇒ 无阻塞字段，正常放行（`blocked` 为空的出口分支）。
    set_current_permission_snapshot(
        PermissionSnapshot(
            field_perms=ConcurrentStableList(
                [FieldPermission(form_id=1, field_key="secret", visible=False, editable=False)]
            )
        )
    )
    assert_fields_writable(form_id=2, values=ConcurrentStableDict({"secret": "x"}))
    with pytest.raises(PermissionError):
        assert_fields_writable(form_id=1, values=ConcurrentStableDict({"secret": "x", "open": "y"}))
    set_current_permission_snapshot(None)
