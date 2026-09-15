"""通知渠道能力域：统一发送契约（真实站内信 / 邮件 / 短信渠道随通知公告阶段回补）。

- `NotifyChannel`：渠道枚举（`inbox` 站内信 / `email` 邮件 / `sms` 短信）。
- `NotificationMessage` / `SendResult`：通知消息与发送结果数据契约（frozen dataclass）。
- `BaseNotifier`：能力域中间层契约（`key = "notifier"`）——异步 `send(message)` 统一发送（按渠道分派）。
- `get_notifier`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：渠道偏好过滤（`sys_user_preference`）、模板落库与按 locale 渲染、发送记录（`sys_mail_log` / `sys_sms_log`）、
站内信落库 + 实时推送（`notification.new`）、短信渠道故障降级均归上层（通知公告阶段）；本契约接收已渲染内容、
只落发送原语。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "NULL_MESSAGE_ID",
    "BaseNotifier",
    "NotificationMessage",
    "NotifyChannel",
    "SendResult",
    "get_notifier",
]

NULL_MESSAGE_ID = "null-message-id"
"""占位消息 id（NullNotifier.send 固定返回，便于断言）。"""


class NotifyChannel(StrEnum):
    """通知渠道。"""

    INBOX = "inbox"
    """站内信（落 `sys_notification` + 触发实时推送）。"""

    EMAIL = "email"
    """邮件（aiosmtplib + Jinja2 模板）。"""

    SMS = "sms"
    """短信（阿里云 / 腾讯云）。"""


@dataclass(frozen=True)
class NotificationMessage(BaseObject):
    """通知消息（内容已按收件人 locale 渲染）。"""

    channel: NotifyChannel
    """通知渠道。"""

    recipient: str
    """收件目标（站内信为用户 id、邮件为邮箱地址、短信为手机号）。"""

    content: str
    """正文内容。"""

    title: str = ""
    """标题 / 邮件主题（短信等无标题渠道可留空）。"""

    biz_type: str | None = None
    """业务类型（如 `approval`；可选）。"""

    biz_id: str | None = None
    """业务 id（供跳转与去重；可选）。"""


@dataclass(frozen=True)
class SendResult(BaseObject):
    """发送结果。"""

    delivered: bool
    """是否发送成功。"""

    message_id: str | None = None
    """渠道回执 id（可选）。"""

    detail: str | None = None
    """失败说明（可选）。"""


class BaseNotifier(BasePluggable, ABC):
    """通知发送契约：按渠道统一发送。"""

    key: str = "notifier"
    plugin_key: str = "notifier"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def send(self, message: NotificationMessage) -> SendResult:
        """统一发送通知（按 `message.channel` 分派到对应渠道）。

        Args:
            message: 通知消息。

        Returns:
            SendResult: 发送结果。
        """


def get_notifier(request: Request) -> BaseNotifier:
    """取应用级通知器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseNotifier: 应用装配的通知器实例。
    """
    return cast("BaseNotifier", request.app.state.notifier)
