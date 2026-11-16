"""JSON 承载（03-6 首发实现迁入 03-6-1，行为不变）：业务字段与消息体都放请求体。

**为什么保留**：帧通道是默认，但回退路径必须在——网关形态、对拍、以及「帧通道出问题要能一条配置切回来」。
两个实现走同一份契约（`transport.MessagingTransport`），调用方无感。

**与帧通道的唯一差别**：消息体走 `payload` 字段的 base64 文本（文本载体必需），字段名与取值完全一致。
"""

from __future__ import annotations

from bms_core.msgclient.messaging.transport import (
    ApiOutcome,
    ApiRequest,
    HttpxChannel,
    encode_payload,
    to_wire,
)

__all__ = ["JsonTransport"]

_JSON_HINT = "响应不是合法 JSON"
"""解析失败提示（与帧通道措辞区分，排障时一眼看出是哪条通道）。"""


class JsonTransport(HttpxChannel):
    """JSON 传输（`application/json`；单实例可被生产端与消费端共享）。"""

    async def post(self, endpoint: str, request: ApiRequest) -> ApiOutcome:
        """发一次 JSON POST 并解析统一响应体。

        Args:
            endpoint: 服务地址（`scheme://host:port`，不带路径）。
            request: 业务请求（`frame_type` 在本通道不参与组装）。

        Returns:
            ApiOutcome: 解析结果。

        Raises:
            MsgClientError: 传输失败或响应不可解析。
        """
        response = await self._post_json(f"{endpoint}{request.path}", self.body(request), self.headers())
        return self._parse_json(response, hint=_JSON_HINT)

    @staticmethod
    def body(request: ApiRequest) -> dict[str, object]:  # bare-collections:allow（httpx 的 json= 只接受内置 dict）
        """组装请求体（业务字段原样 + 消息体 base64）。

        Args:
            request: 业务请求。

        Returns:
            dict[str, object]: 请求体。
        """
        # bare-collections:allow（httpx 的 json= 只接受内置 dict）
        body: dict[str, object] = {str(key): to_wire(value) for key, value in request.fields.items()}
        if request.payload:
            body["payload"] = encode_payload(request.payload)
        return body
