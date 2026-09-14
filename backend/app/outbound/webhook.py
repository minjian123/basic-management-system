"""出站集成能力域 · Webhook：投递契约（真实投递随系统集成阶段回补）。

- `WebhookResult`：投递结果数据契约（frozen）。
- `BaseWebhookSender`：能力域中间层契约（`key = "webhook_sender"`）——异步 `send`（签名 / 重试由实现内部处理）。
- `NullWebhookSender`：占位实现——固定返回投递成功（**不外呼**）。
- `get_webhook_sender`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

签名口径：真实实现按出站口径 `sha256(secret, body)` 经 `core/security.py` 的 `SignatureCodec` 计算
（与本任务前置契约 02-3-10 一致，不另写 HMAC）；指数退避重试与 `sys_webhook_log` 失败记录归上层（系统集成阶段）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject

__all__ = [
    "BaseWebhookSender",
    "NullWebhookSender",
    "WebhookResult",
    "get_webhook_sender",
]


@dataclass(frozen=True)
class WebhookResult(BaseObject):
    """投递结果数据契约。"""

    delivered: bool
    """是否投递成功。"""

    status_code: int | None = None
    """响应状态码（可选）。"""

    attempts: int = 1
    """实际尝试次数。"""


class BaseWebhookSender(BaseCapability, ABC):
    """Webhook 投递契约：签名 / 投递 / 重试（后两者由实现内部处理）。"""

    key: str = "webhook_sender"

    @abstractmethod
    async def send(self, url: str, payload: Mapping[str, object], *, secret: str | None = None) -> WebhookResult:
        """投递 Webhook。

        Args:
            url: 目标地址。
            payload: 载荷（真实实现序列化为 JSON body）。
            secret: 签名密钥（可选；真实实现按 `sha256(secret, body)` 签名）。

        Returns:
            WebhookResult: 投递结果。
        """


class NullWebhookSender(BaseWebhookSender, BaseNullObject):
    """占位 Webhook 发送器：固定返回投递成功（不外呼，未接入真实实现时使用）。"""

    async def send(self, url: str, payload: Mapping[str, object], *, secret: str | None = None) -> WebhookResult:
        """恒定返回投递成功（不外呼）。

        Args:
            url: 目标地址（占位忽略）。
            payload: 载荷（占位忽略）。
            secret: 签名密钥（占位忽略）。

        Returns:
            WebhookResult: 成功结果（`delivered=True`、`status_code=200`、`attempts=1`）。
        """
        return WebhookResult(delivered=True, status_code=200, attempts=1)


def get_webhook_sender(request: Request) -> BaseWebhookSender:
    """取应用级 Webhook 发送器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseWebhookSender: 应用装配的发送器实例。
    """
    return cast("BaseWebhookSender", request.app.state.webhook_sender)
