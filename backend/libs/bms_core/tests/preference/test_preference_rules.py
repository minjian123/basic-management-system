"""用户偏好键与值规则（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

import pytest

from bms_core.core.exceptions import PreferenceDndInvalidError, PreferenceKeyInvalidError, PreferenceValueInvalidError
from bms_core.preference.base import PREF_VALUE_MAX_BYTES
from bms_core.preference.rules import (
    _parse_hm,
    is_allowed_pref_key,
    validate_notify_channels,
    validate_notify_dnd,
    validate_pref_value,
)

pytestmark = pytest.mark.kiwi_id(2517)


def test_allowed_pref_keys() -> None:
    """允许域内键通过，未知域 / 非法格式拒绝。"""
    assert is_allowed_pref_key("notify.channels")
    assert is_allowed_pref_key("list.user_form")
    assert is_allowed_pref_key("ui.theme")
    assert not is_allowed_pref_key("unknown.key")
    assert not is_allowed_pref_key("bad")


def test_validate_pref_value_serializes() -> None:
    """普通值序列化为紧凑 JSON。"""
    assert validate_pref_value("ui.theme", {"mode": "dark"}) == '{"mode":"dark"}'


def test_validate_pref_value_rejects_key_and_size() -> None:
    """非法键 / 超限值 / 不可序列化值拒绝。"""
    with pytest.raises(PreferenceKeyInvalidError):
        validate_pref_value("unknown.key", 1)
    with pytest.raises(PreferenceValueInvalidError):
        validate_pref_value("ui.theme", "x" * (PREF_VALUE_MAX_BYTES + 1))
    with pytest.raises(PreferenceValueInvalidError):
        validate_pref_value("ui.theme", object())


def test_validate_channels() -> None:
    """渠道开关结构校验。"""
    validate_notify_channels({"inbox": False})
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_channels(["inbox"])
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_channels({"bad": True})
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_channels({"inbox": "yes"})


def test_validate_dnd() -> None:
    """免打扰结构 / 时间格式 / 起止校验。"""
    validate_notify_dnd({"enabled": True, "start": "22:00", "end": "08:00"})
    validate_notify_dnd({"enabled": False})
    assert validate_pref_value("notify.dnd", {"enabled": True, "start": "22:00", "end": "08:00"})
    assert _parse_hm("8:05") is not None
    assert _parse_hm("8:5") is not None
    assert _parse_hm("24:00") is None
    assert _parse_hm(None) is None  # pyright: ignore[reportArgumentType]
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_dnd(["x"])
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_dnd({"enabled": "yes"})
    with pytest.raises(PreferenceValueInvalidError):
        validate_notify_dnd({"start": 1})
    with pytest.raises(PreferenceDndInvalidError):
        validate_notify_dnd({"enabled": True, "start": "25:00", "end": "08:00"})
    with pytest.raises(PreferenceDndInvalidError):
        validate_notify_dnd({"enabled": True, "start": "10:00", "end": "10:00"})
