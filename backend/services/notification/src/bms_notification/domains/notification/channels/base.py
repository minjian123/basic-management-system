"""邮件 / 短信真实通道协议与结果。

通道实现只负责「把已渲染内容交给外部服务」，不做模板、偏好、日志与重试；
这些由外发调度器与作业中心统一负责。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject

__all__ = ["BaseMailChannel", "BaseSmsChannel", "ChannelResult"]


@dataclass(frozen=True)
class ChannelResult(BaseValueObject):
    """通道发送结果。"""

    delivered: bool
    """是否送达（或已被厂商受理）。"""

    provider_message_id: str | None = None
    """厂商回执 ID。"""

    error: str | None = None
    """失败原因（截断后落日志）。"""

    retryable: bool = True
    """失败是否可重试（瞬时故障为 True；模板 / 签名 / 认证错误为 False）。"""


class BaseMailChannel(ABC):
    """邮件通道协议。"""

    @abstractmethod
    async def send(self, *, recipient: str, subject: str, content: str, html: bool) -> ChannelResult:
        """发送一封邮件。

        Args:
            recipient: 收件邮箱。
            subject: 主题。
            content: 正文（HTML 或纯文本）。
            html: 正文是否 HTML。

        Returns:
            ChannelResult: 发送结果。
        """


class BaseSmsChannel(ABC):
    """短信通道协议。"""

    @abstractmethod
    async def send(
        self,
        *,
        phone: str,
        provider_template_id: str,
        params: ConcurrentStableDict[str, str],
        param_keys: ConcurrentStableList[str],
    ) -> ChannelResult:
        """发送一条模板短信。

        Args:
            phone: 手机号（通道内部按厂商要求归一）。
            provider_template_id: 厂商模板 ID。
            params: 参数键值。
            param_keys: 参数顺序（腾讯按数组顺序；阿里云按键名）。

        Returns:
            ChannelResult: 发送结果。
        """
