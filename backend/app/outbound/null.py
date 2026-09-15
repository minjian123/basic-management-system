"""outbound 能力域缺省实现（Null Object）：占位返回、无副作用
（02-3 自 app.outbound.http.py、app.outbound.webhook.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.outbound.http import BaseHttpClient, HttpResponse
from app.outbound.webhook import BaseWebhookSender, WebhookResult

__all__ = [
    "NullHttpClient",
    "NullWebhookSender",
]


class NullHttpClient(BaseHttpClient, BaseNullObject):
    """占位 HTTP 客户端：固定返回成功响应（不外呼，未接入真实实现时使用）。"""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        timeout: int | None = None,
    ) -> HttpResponse:
        """恒定返回成功响应（不外呼）。

        Args:
            method: HTTP 方法（占位忽略）。
            url: 目标地址（占位忽略）。
            headers: 请求头（占位忽略）。
            content: 请求体（占位忽略）。
            timeout: 超时（占位忽略）。

        Returns:
            HttpResponse: 成功响应（`status_code=200`、空头 / 空 body）。
        """
        return HttpResponse(status_code=200, headers={}, content=b"")


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
