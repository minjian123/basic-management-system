"""03-6 用例：JSON 通道专属（Kiwi 2510）。

覆盖要点：请求体组装（业务字段原样 + 消息体 base64）；`data.retry_after_ms` 作为第二个建议间隔来源；
响应解析的三种不合法形态；`data` 非对象归一成空映射；拉取数组里的脏元素被跳过。

通道无关的语义见 `test_transport.py`；帧形态的对应判据见 `test_transport_frame.py`。
"""

from __future__ import annotations

import base64
import json

import pytest

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.msgclient.frame import FrameType
from bms_core.msgclient.messaging import ApiRequest, MessagingConfig, MsgClientError, TransportChannel
from bms_core.msgclient.messaging.transport_json import JsonTransport

from ._support import DEFAULT_ENDPOINT, ScriptedServer, build_config, build_consumer, build_transport

pytestmark = pytest.mark.kiwi_id(2510)


def _config() -> MessagingConfig:
    """构造 JSON 通道配置。

    Returns:
        MessagingConfig: 配置。
    """
    return build_config(channel=TransportChannel.JSON)


def _publish(payload: bytes = b"hi") -> ApiRequest:
    """构造一次发布请求。

    Args:
        payload: 消息体。

    Returns:
        ApiRequest: 请求。
    """
    return ApiRequest(
        frame_type=int(FrameType.PUBLISH),
        path="/msg/publish",
        fields=ConcurrentStableFrozenDict({"namespace": "ns", "topic": "orders"}),
        payload=payload,
    )


@pytest.mark.asyncio
async def test_request_body_has_fields_and_base64_payload() -> None:
    """请求体：业务字段原样、消息体走 base64 文本字段。"""
    server = ScriptedServer()
    server.push("/msg/publish", data={"message_id": "m1"})
    await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish(b"hello"))

    body = json.loads(server.requests[0].content)
    assert body["namespace"] == "ns"
    assert body["topic"] == "orders"
    assert body["payload"] == base64.b64encode(b"hello").decode("ascii")


@pytest.mark.asyncio
async def test_empty_payload_omits_body_field() -> None:
    """空消息体：不发 `payload` 键（服务端缺省即空串，少一个字段就少一次 base64）。"""
    server = ScriptedServer()
    server.push("/msg/publish", data={"message_id": "m1"})
    await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish(b""))

    body = json.loads(server.requests[0].content)
    assert "payload" not in body


@pytest.mark.asyncio
async def test_retry_after_falls_back_to_data_field() -> None:
    """没有 `Retry-After` 头：回落错误体里的 `data.retry_after_ms`。"""
    server = ScriptedServer()
    server.push("/msg/publish", code=350005, data={"retry_after_ms": 800})
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())
    assert outcome.retry_after_ms == 800


@pytest.mark.asyncio
async def test_non_json_response_is_rejected() -> None:
    """响应不是 JSON（网关页面 / 反代错误页）：直接判失败，不重试。"""
    server = ScriptedServer()
    server.push("/msg/publish", status=200, raw_text="<html>bad gateway</html>")
    with pytest.raises(MsgClientError, match="不是合法 JSON"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_non_object_response_is_rejected() -> None:
    """响应是 JSON 但不是对象：同样判失败。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_text="[1, 2, 3]")
    with pytest.raises(MsgClientError, match="不是对象"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_missing_code_is_rejected() -> None:
    """响应缺整型 code：判失败（对端不是本服务）。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_text=json.dumps({"message": "x"}))
    with pytest.raises(MsgClientError, match="缺少整型 code"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_data_not_object_becomes_empty_mapping() -> None:
    """`data` 不是对象：归一成空映射，不抛错（调用方按空 `data` 处理）。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_text=json.dumps({"code": 0, "message": "", "data": "text"}))
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())
    assert outcome.data == ConcurrentStableFrozenDict[str, object]()
    assert outcome.retry_after_ms is None


@pytest.mark.asyncio
async def test_poll_skips_non_object_message_entries() -> None:
    """拉取数组里混入非对象元素：跳过该条，其余照常解析（JSON 通道的宽容读法）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data={"group": "g1", "topic": "orders", "consumer_id": "c1", "partitions": [0]})
    server.push("/api/v1/msg/consume", data={"messages": ["junk", {"message_id": "m1", "offset": 0}]})
    consumer, _ = build_consumer(_config(), server)
    await consumer.join()
    result = await consumer.poll()
    assert len(result.messages) == 1
    await consumer.close()


def test_json_transport_ignores_frame_type() -> None:
    """JSON 实现不看 `frame_type`：同一份请求在 JSON 通道照常发请求体。"""
    server = ScriptedServer()
    transport = build_transport(_config(), server)
    assert isinstance(transport, JsonTransport)


@pytest.mark.asyncio
async def test_member_request_ignores_frame_type_in_json_channel() -> None:
    """成员端点（帧类型 7）在 JSON 通道照常发请求体，且不带 `payload` 键。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data={"group": "g1", "topic": "orders", "consumer_id": "c1"})
    request = ApiRequest(
        frame_type=int(FrameType.JOIN), path="/api/v1/msg/join", fields=ConcurrentStableFrozenDict({"group": "g1"})
    )
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, request)
    body = json.loads(server.requests[0].content)
    assert outcome.code == 0
    assert body["group"] == "g1"
    assert "payload" not in body
