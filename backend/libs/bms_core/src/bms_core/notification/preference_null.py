"""通知偏好读取缺省实现（Null Object）：全渠道开启、免打扰关闭，不读库 / 不发请求。"""

from bms_core.core.capability import BaseNullObject
from bms_core.notification.preference import (
    BaseNotificationPreferenceStore,
    NotificationPreference,
    default_notification_preference,
)

__all__ = ["NullNotificationPreferenceStore"]


class NullNotificationPreferenceStore(BaseNotificationPreferenceStore, BaseNullObject):
    """占位通知偏好读取：恒返回默认偏好。"""

    async def load(self, user_id: int) -> NotificationPreference:
        """读取指定用户偏好（占位恒默认）。

        Args:
            user_id: 收件用户主键（占位忽略）。

        Returns:
            NotificationPreference: 默认偏好。
        """
        del user_id
        return default_notification_preference()
