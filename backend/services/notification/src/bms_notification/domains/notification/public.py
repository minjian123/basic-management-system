"""通知业务域公共出口（D2 唯一跨域引用面）。

07_02（公告）/ 07_03（邮件短信）如需在通知服务内复用通知请求契约，经本出口导入；
域内实现文件不得被跨域直接导入（D1 拦截）。
"""

from bms_core.notification.request import NotificationRequest
from bms_core.notification.types import NOTIFICATION_TYPE_APPROVAL, NOTIFICATION_TYPES
from bms_notification.domains.notification.notice_constants import (
    NOTICE_ACTIONS,
    NOTICE_STATUS_DRAFT,
    NOTICE_STATUS_OFFLINE,
    NOTICE_STATUS_PUBLISHED,
    NOTICE_STATUSES,
)

__all__ = [
    "NOTICE_ACTIONS",
    "NOTICE_STATUSES",
    "NOTICE_STATUS_DRAFT",
    "NOTICE_STATUS_OFFLINE",
    "NOTICE_STATUS_PUBLISHED",
    "NOTIFICATION_TYPES",
    "NOTIFICATION_TYPE_APPROVAL",
    "NotificationRequest",
]
