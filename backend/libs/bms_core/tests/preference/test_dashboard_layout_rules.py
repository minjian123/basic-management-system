"""偏好基座：工作台个人布局结构校验（Kiwi 2528）。"""

import pytest

from bms_core.core.exceptions import PreferenceValueInvalidError
from bms_core.preference.rules import validate_pref_value

pytestmark = pytest.mark.kiwi_id(2528)


def test_dashboard_layout_accepts_valid_structure() -> None:
    """合法布局（含空布局）通过并序列化。"""
    serialized = validate_pref_value(
        "dashboard.layout", {"cards": [{"code": "todo", "x": 0, "y": 0, "w": 4, "h": 2, "visible": True}]}
    )
    assert '"todo"' in serialized
    assert validate_pref_value("dashboard.layout", {"cards": []}) == '{"cards":[]}'


def test_dashboard_layout_rejects_invalid_structure() -> None:
    """结构非法 / 越界 / 重叠 / 重复码一律 `30022`（偏好值非法）。"""
    with pytest.raises(PreferenceValueInvalidError) as not_object:
        validate_pref_value("dashboard.layout", "not-an-object")
    assert "structure" in str(not_object.value)

    with pytest.raises(PreferenceValueInvalidError) as out_of_range:
        validate_pref_value("dashboard.layout", {"cards": [{"code": "todo", "w": 1, "h": 9}]})
    assert "width-out-of-range" in str(out_of_range.value)

    with pytest.raises(PreferenceValueInvalidError) as overlap:
        validate_pref_value(
            "dashboard.layout",
            {"cards": [{"code": "todo", "x": 0, "y": 0, "w": 6, "h": 2}, {"code": "notice", "x": 2, "y": 1}]},
        )
    assert "overlap" in str(overlap.value)

    with pytest.raises(PreferenceValueInvalidError) as duplicate:
        validate_pref_value("dashboard.layout", {"cards": [{"code": "todo"}, {"code": "todo"}]})
    assert "duplicate-code" in str(duplicate.value)


def test_other_keys_unaffected() -> None:
    """其他偏好键不受工作台校验影响（`ui.*` 任意对象可写）。"""
    assert validate_pref_value("ui.tabs", {"tabsEnabled": True}) != ""
