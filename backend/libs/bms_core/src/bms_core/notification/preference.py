"""通知偏好能力域：按收件人读取渠道开关与免打扰时段。

- `NotificationPreference`：值对象（渠道开关 / 免打扰 / 时区），提供渠道判定与时段判定。
- `BaseNotificationPreferenceStore`：能力域中间层契约（`key = "notification_preference"`）——
  异步 `load(user_id)`；**按收件人**读取，不复用只有当前用户维度的 `BasePreferenceStore`。
- `get_notification_preference_store`：依赖注入提供者（应用级单例）。

口径：读不到偏好时回落「全渠道开启、无免打扰」（通知不得因偏好抖动而不落库）；
免打扰只影响实时推送，站内信仍落库。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.config import Settings, get_settings
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.i18n.timezone import to_local

__all__ = [
    "DND_DISABLED",
    "NOTIFY_PREF_CHANNELS",
    "NOTIFY_PREF_DND",
    "BaseNotificationPreferenceStore",
    "NotificationPreference",
    "default_notification_preference",
    "get_notification_preference_store",
]

NOTIFY_PREF_CHANNELS = "notify.channels"
"""渠道开关偏好键。"""

NOTIFY_PREF_DND = "notify.dnd"
"""免打扰偏好键。"""

DND_DISABLED = "00:00"
"""免打扰关闭时的占位起止时间（不参与判定）。"""


def default_notification_preference() -> NotificationPreference:
    """默认通知偏好（全渠道开启、无免打扰、使用系统兜底时区）。

    Returns:
        NotificationPreference: 默认偏好。
    """
    return NotificationPreference(
        channels=ConcurrentStableFrozenDict({"inbox": True, "email": True, "sms": True}),
        dnd_enabled=False,
        dnd_start=DND_DISABLED,
        dnd_end=DND_DISABLED,
        timezone=None,
    )


@dataclass(frozen=True)
class NotificationPreference(BaseValueObject):
    """通知偏好（渠道开关 + 免打扰时段 + 判定时区）。"""

    channels: ConcurrentStableFrozenDict[str, bool] = field(
        default_factory=lambda: ConcurrentStableFrozenDict({"inbox": True, "email": True, "sms": True})
    )
    """渠道开关（`inbox` / `email` / `sms`；缺键按开启处理）。"""

    dnd_enabled: bool = False
    """是否启用免打扰。"""

    dnd_start: str = DND_DISABLED
    """免打扰开始（`HH:MM`）。"""

    dnd_end: str = DND_DISABLED
    """免打扰结束（`HH:MM`）。"""

    timezone: str | None = None
    """判定时区（IANA；None 取 `[i18n].default_timezone`）。"""

    def channel_enabled(self, channel: str) -> bool:
        """渠道是否开启（缺键按开启）。

        Args:
            channel: 渠道名（`inbox` / `email` / `sms`）。

        Returns:
            bool: 开启为 True。
        """
        return bool(self.channels.get(channel, True))

    def in_quiet_hours(self, now_utc: datetime) -> bool:
        """当前 UTC 时刻是否落在免打扰时段。

        Args:
            now_utc: 当前 UTC 时间（naive）。

        Returns:
            bool: 命中免打扰为 True；未启用、时间格式非法或时区非法均 False。
        """
        if not self.dnd_enabled:
            return False
        start = _parse_hm(self.dnd_start)
        end = _parse_hm(self.dnd_end)
        if start is None or end is None or start == end:
            return False
        timezone_name = self.timezone or get_settings().i18n_options.default_timezone
        try:
            local = to_local(now_utc, timezone_name)
        except ValueError:
            local = now_utc
        current = local.time()
        if start < end:
            return start <= current <= end
        return current >= start or current <= end


def _parse_hm(value: str) -> time | None:
    """解析 `HH:MM`。

    Args:
        value: 时间字符串。

    Returns:
        time | None: 解析结果；非法为 None。
    """
    try:
        hour_text, minute_text = value.strip().split(":", 1)
        return time(int(hour_text), int(minute_text))
    except ValueError, AttributeError:
        return None


class BaseNotificationPreferenceStore(BasePluggable, ABC):
    """通知偏好读取契约：按收件人取渠道开关与免打扰。"""

    key: str = "notification_preference"
    plugin_key: str = "notification_preference"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def load(self, user_id: int) -> NotificationPreference:
        """读取指定用户的偏好（读不到回落默认）。

        Args:
            user_id: 收件用户主键。

        Returns:
            NotificationPreference: 通知偏好。
        """


def get_notification_preference_store(request: Request) -> BaseNotificationPreferenceStore:
    """取应用级通知偏好读取实现（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseNotificationPreferenceStore: 应用装配的实现实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseNotificationPreferenceStore",
        resolve_plugin(
            "notification_preference",
            settings.notification_preference.provider,
            expected_version=BaseNotificationPreferenceStore.contract_version,
        ),
    )
