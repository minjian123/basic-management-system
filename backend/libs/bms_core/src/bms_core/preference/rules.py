"""用户偏好键与值规则：允许前缀、JSON 大小、通知偏好结构校验。

- 键规范沿用 `bms_core/preference/base.py::is_valid_pref_key`（`{域}.{键}`）。
- 允许域名：`ui` / `list` / `notify` / `dashboard` / `wizard`（未知域拒绝，防脏数据）。
- 通知偏好结构：
  - `notify.channels`：`{inbox, email, sms}` → 布尔（缺键按开启）；
  - `notify.dnd`：`{enabled, start, end}`，时间为 `HH:MM`，启用时 `start != end`。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import time
from typing import cast

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.exceptions import PreferenceDndInvalidError, PreferenceKeyInvalidError, PreferenceValueInvalidError
from bms_core.dashboard.layout import CardSize, parse_layout
from bms_core.preference.base import PREF_VALUE_MAX_BYTES, is_valid_pref_key

__all__ = [
    "NOTIFY_CHANNELS",
    "PREFERENCE_DOMAINS",
    "is_allowed_pref_key",
    "validate_dashboard_layout",
    "validate_notify_channels",
    "validate_notify_dnd",
    "validate_pref_value",
]

PREFERENCE_DOMAINS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
    ("ui", "list", "notify", "dashboard", "wizard")
)
"""允许的偏好域名（首段）。"""

NOTIFY_CHANNELS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("inbox", "email", "sms"))
"""通知渠道清单。"""


def is_allowed_pref_key(key: str) -> bool:
    """校验偏好键是否允许写入。

    Args:
        key: 偏好键。

    Returns:
        bool: 格式合法且首段在允许域内为 True。
    """
    if not is_valid_pref_key(key):
        return False
    return key.split(".", 1)[0] in PREFERENCE_DOMAINS


def validate_pref_value(key: str, value: object) -> str:
    """校验并序列化偏好值。

    Args:
        key: 偏好键。
        value: 偏好值（JSON 可序列化）。

    Returns:
        str: JSON 字符串。

    Raises:
        PreferenceKeyInvalidError: 键不在允许范围（`30021`）。
        PreferenceValueInvalidError: 值不可序列化或超限（`30022`）。
        PreferenceDndInvalidError: 免打扰结构非法（`30024`）。
    """
    if not is_allowed_pref_key(key):
        raise PreferenceKeyInvalidError(f"偏好键不在允许范围：{key}")
    if key == "notify.channels":
        validate_notify_channels(value)
    elif key == "notify.dnd":
        validate_notify_dnd(value)
    elif key == "dashboard.layout":
        validate_dashboard_layout(value)
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise PreferenceValueInvalidError(f"偏好值不可序列化：{key}") from exc
    if len(serialized.encode("utf-8")) > PREF_VALUE_MAX_BYTES:
        raise PreferenceValueInvalidError(f"偏好值超出 {PREF_VALUE_MAX_BYTES} 字节：{key}")
    return serialized


def validate_notify_channels(value: object) -> None:
    """校验渠道开关结构。

    Args:
        value: 偏好值。

    Raises:
        PreferenceValueInvalidError: 非对象、未知渠道或值非布尔（`30022`）。
    """
    if not isinstance(value, Mapping):
        raise PreferenceValueInvalidError("notify.channels 应为对象")
    for key, item in cast("Mapping[object, object]", value).items():
        name = str(key)
        if name not in NOTIFY_CHANNELS:
            raise PreferenceValueInvalidError(f"notify.channels 含未知渠道：{name}")
        if not isinstance(item, bool):
            raise PreferenceValueInvalidError(f"notify.channels.{name} 应为布尔")


def validate_notify_dnd(value: object) -> None:
    """校验免打扰结构。

    Args:
        value: 偏好值。

    Raises:
        PreferenceValueInvalidError: 非对象或字段类型非法（`30022`）。
        PreferenceDndInvalidError: 时间格式非法或起止相同（`30024`）。
    """
    if not isinstance(value, Mapping):
        raise PreferenceValueInvalidError("notify.dnd 应为对象")
    mapping = cast("Mapping[str, object]", value)
    enabled = mapping.get("enabled", False)
    if not isinstance(enabled, bool):
        raise PreferenceValueInvalidError("notify.dnd.enabled 应为布尔")
    start = mapping.get("start", "00:00")
    end = mapping.get("end", "00:00")
    if not isinstance(start, str) or not isinstance(end, str):
        raise PreferenceValueInvalidError("notify.dnd.start / end 应为字符串")
    start_time = _parse_hm(start)
    end_time = _parse_hm(end)
    if start_time is None or end_time is None:
        raise PreferenceDndInvalidError("免打扰时间格式应为 HH:MM")
    if enabled and start_time == end_time:
        raise PreferenceDndInvalidError("免打扰起止时间不得相同")


def _parse_hm(value: str) -> time | None:
    """解析 `HH:MM`。

    Args:
        value: 时间字符串。

    Returns:
        time | None: 解析结果；非法为 None。
    """
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError, AttributeError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def validate_dashboard_layout(value: object) -> None:
    """校验工作台个人布局结构（`dashboard.layout`）。

    **为什么在基座校验**（11_01 决策 5）：个人布局除工作台保存入口外，还可能经偏好通用接口或移动端写入；
    校验放在基座可保证任何写入路径都拦非法配置，不会出现「绕过工作台写坏布局」。

    Args:
        value: 偏好值（应为 `{"cards": [{code, x, y, w, h, visible}]}`）。

    Raises:
        PreferenceValueInvalidError: 结构非法（`30022`，含逐项原因）。
    """
    size_map: ConcurrentStableFrozenDict[str, CardSize] = ConcurrentStableFrozenDict({})
    _layout, issues = parse_layout(value, sizes=size_map)
    if not issues:
        return
    descriptions: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(
        f"{issue.code or '-'}:{issue.reason}" for issue in issues
    )
    raise PreferenceValueInvalidError("工作台布局结构非法：" + "、".join(descriptions))
