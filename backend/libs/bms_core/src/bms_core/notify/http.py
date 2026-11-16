"""通知发送真实实现（`http`）：经 `service_client` 调通知服务内部发送端点。

- **权威侧是 notification 服务**（模板 / 日志 / 渠道 / 异步作业 / 重试全在其内）。
- **契约**：`POST /api/v1/mail/internal/send`（服务 JWT + `notification.send` 能力 / identity 白名单）。
- **短信**：云短信只允许厂商已审核模板，必须带 `template_code` 与 `params`；缺模板直接判未送达，不发起调用。
- **降级**：不可达 / 超时 / 非 2xx / 载荷非法 → `SendResult(delivered=False, detail=...)`，由调用方按既有语义返回 503。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION
from bms_core.notify.base import BaseNotifier, NotificationMessage, SendResult
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest

__all__ = ["INTERNAL_SEND_PATH", "NOTIFICATION_SERVICE", "HttpNotifier"]

NOTIFICATION_SERVICE = "notification"
"""发送权威服务标识。"""

INTERNAL_SEND_PATH = "/api/v1/mail/internal/send"
"""内部发送契约路径。"""

_LOGGER = get_logger("bms")


class HttpNotifier(BaseNotifier):
    """经通知服务内部端点发送的通知器（真实实现）。"""

    plugin_name: str = "http"
    contract_version: str = DEFAULT_CONTRACT_VERSION

    def __init__(self, *, client: BaseServiceClient) -> None:
        """初始化。

        Args:
            client: 服务间调用客户端（`service_client` 能力域）。
        """
        self._client = client

    async def send(self, message: NotificationMessage) -> SendResult:
        """发送一条通知消息（短信必须带模板）。

        Args:
            message: 通知消息。

        Returns:
            SendResult: 发送结果；`delivered=True` 表示已受理（异步发送）。
        """
        if message.channel.value == "inbox":
            return SendResult(delivered=False, detail="通知器不支持站内信渠道")
        if message.channel.value == "sms" and not message.template_code:
            return SendResult(delivered=False, detail="短信发送必须提供 template_code")
        body: ConcurrentStableFrozenDict[str, object] = ConcurrentStableFrozenDict(
            {
                "channel": message.channel.value,
                "recipient": message.recipient,
                "title": message.title,
                "content": message.content,
                "template_code": message.template_code,
                "params": dict(message.params) if message.params else {},
                "biz_type": message.biz_type,
                "biz_id": message.biz_id,
                "transactional": True,
            }
        )
        request = ServiceRequest(
            service=NOTIFICATION_SERVICE,
            method="POST",
            path=INTERNAL_SEND_PATH,
            tenant_id=get_current_tenant_id(),
            json_body=body,
        )
        try:
            response = await self._client.call(request)
        except ServiceUnavailableError as exc:
            _LOGGER.warning("通知发送服务不可达", channel=message.channel.value, error=str(exc))
            return SendResult(delivered=False, detail="通知发送服务不可达")
        if not 200 <= response.status_code < 300:
            _LOGGER.warning("通知发送服务返回失败", channel=message.channel.value, status=response.status_code)
            return SendResult(delivered=False, detail=f"通知发送服务返回 {response.status_code}")
        return _parse_result(response.payload(), channel=message.channel.value)


def _parse_result(payload: object, *, channel: str) -> SendResult:
    """解析内部发送端点响应。

    Args:
        payload: 响应体。
        channel: 渠道（日志用）。

    Returns:
        SendResult: 发送结果。
    """
    data: object = None
    if isinstance(payload, Mapping):
        data = cast("Mapping[str, object]", payload).get("data")
    if not isinstance(data, Mapping):
        return SendResult(delivered=False, detail="通知发送服务响应非法")
    row = cast("Mapping[str, object]", data)
    log_id = row.get("log_id")
    status = row.get("status")
    if not isinstance(log_id, str) or not isinstance(status, str):
        return SendResult(delivered=False, detail="通知发送服务响应非法")
    if status != "pending":
        return SendResult(delivered=False, message_id=log_id, detail=f"发送请求未受理（{status}）")
    _LOGGER.info("通知发送已受理", channel=channel, log_id=log_id)
    return SendResult(delivered=True, message_id=log_id, detail="accepted")
