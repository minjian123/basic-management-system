"""03-6-1 用例：帧通道专属（Kiwi 2513）。

覆盖要点：请求形态（帧媒体类型、`request_id` 必填、消息体只在 payload 段、幂等键在帧头 `headers`）；
拉取结果按 `messages[i].length` 切片重组与三类装配错误的拒绝；错误帧 `detail` / `retry_after_ms` 还原；
网关拦截时的 JSON 兜底与彻底不可解析的判定；编码期超限拒绝（零请求）；成员端点同样走帧。

通道无关的语义（重试分类、改投、幂等表、批量、消费生命周期）在 `test_producer.py` / `test_consumer.py`
里按通道参数化各跑一遍，本文件只放帧形态独有的判据。
"""

from __future__ import annotations

import json

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.frame import (
    FRAME_CONTENT_TYPE,
    FrameFlags,
    FrameType,
    decode_frames,
    encode_frame,
)
from bms_core.msgclient.messaging import (
    ApiRequest,
    ClientAction,
    ClientStats,
    FrameTransport,
    JsonTransport,
    MessagingConfig,
    MsgClientError,
    MsgProducer,
    OutgoingMessage,
    TransportChannel,
)
from bms_core.msgclient.messaging.transport_factory import build_transport as build_channel_transport

from ._support import DEFAULT_ENDPOINT, ScriptedServer, build_config, build_transport

pytestmark = pytest.mark.kiwi_id(2513)

_FIELDS: ConcurrentStableFrozenDict[str, object] = ConcurrentStableFrozenDict({"namespace": "ns", "topic": "orders"})


def _config() -> MessagingConfig:
    """构造帧通道配置。

    Returns:
        MessagingConfig: 配置。
    """
    return build_config(channel=TransportChannel.FRAME)


def _publish(payload: bytes = b"hello") -> ApiRequest:
    """构造一次发布请求。

    Args:
        payload: 消息体。

    Returns:
        ApiRequest: 请求。
    """
    return ApiRequest(
        frame_type=int(FrameType.PUBLISH),
        path="/msg/publish",
        fields=_FIELDS,
        payload=payload,
    )


def _consume() -> ApiRequest:
    """构造一次拉取请求（服务端必填字段齐备）。

    Returns:
        ApiRequest: 请求。
    """
    return ApiRequest(
        frame_type=int(FrameType.CONSUME),
        path="/api/v1/msg/consume",
        fields=ConcurrentStableFrozenDict(
            {"group": "g1", "consumer_id": "c1", "namespace": "ns", "topic": "orders", "partition": 0}
        ),
    )


def _frame(frame_type: int, header: ConcurrentStableFrozenDict[str, object], payload: bytes = b"") -> bytes:
    """手工编一帧响应（构造畸形 / 边界响应）。

    Args:
        frame_type: 帧类型。
        header: 帧头。
        payload: payload 段。

    Returns:
        bytes: 帧字节。
    """
    return encode_frame(frame_type=frame_type, flags=FrameFlags.RESPONSE, header=header, payload=payload)


def _meta(**overrides: object) -> ConcurrentStableFrozenDict[str, object]:
    """构造一条消息元数据。

    Args:
        overrides: 覆盖字段。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 元数据。
    """
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"message_id": "m1", "topic": "orders", "partition": 0, "offset": 0}
    )
    for key, value in overrides.items():
        values.set(key, value)
    return ConcurrentStableFrozenDict(values)


@pytest.mark.asyncio
async def test_request_is_a_single_frame_with_request_id_and_raw_payload() -> None:
    """请求形态：帧媒体类型、单帧、`request_id` 必填、消息体只在 payload 段、帧头无 `payload` 键。"""
    server = ScriptedServer()
    server.push("/msg/publish", data={"message_id": "m1"})
    await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish(b"hello"))

    request = server.requests[0]
    assert request.headers["content-type"].split(";")[0] == FRAME_CONTENT_TYPE
    frames = decode_frames(request.content).frames
    assert len(frames) == 1
    frame = frames[0]
    assert frame.frame_type == int(FrameType.PUBLISH)
    assert isinstance(frame.header.get("request_id"), str)
    assert frame.header.get("request_id")
    assert "payload" not in frame.header
    assert bytes(frame.payload) == b"hello"


@pytest.mark.asyncio
async def test_idempotency_key_lands_in_frame_headers() -> None:
    """幂等键落帧头 `headers` 映射（与 JSON 请求体的 `headers` 同构，服务端随消息存储）。"""
    server = ScriptedServer()
    server.push("/msg/publish", data={"message_id": "m1"})
    producer = MsgProducer(_config(), build_transport(_config(), server), ClientStats())
    await producer.publish(OutgoingMessage(namespace="ns", topic="orders", payload=b"x", idempotency_key="idem-9"))
    frame = decode_frames(server.requests[0].content).frames[0]
    headers = frame.header["headers"]
    assert isinstance(headers, dict)
    assert headers["x-msg-idem-key"] == "idem-9"
    assert "payload" not in frame.header


@pytest.mark.asyncio
async def test_consume_payload_is_split_by_length() -> None:
    """拉取结果：payload 段按 `messages[i].length` 切片，`payload_segments` 与元数据一一对应。"""
    server = ScriptedServer()
    server.push(
        "/api/v1/msg/consume",
        data={"messages": [_meta(offset=0), _meta(message_id="m2", offset=1)], "paused": True, "inflight_bytes": 5},
        payloads=ConcurrentStableFrozenList([b"abc", b"de"]),
    )
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _consume())

    assert list(outcome.payload_segments) == [b"abc", b"de"]
    assert [len(segment) for segment in outcome.payload_segments] == [3, 2]
    assert outcome.data.get("count") == 2
    assert outcome.data.get("paused") is True
    assert outcome.data.get("inflight_bytes") == 5


@pytest.mark.asyncio
async def test_consume_length_mismatch_is_server_bug() -> None:
    """元数据合计长度与 payload 总长不符：判对端装配错误（不重试）。"""
    server = ScriptedServer()
    server.push(
        "/api/v1/msg/consume",
        raw_content=_frame(
            int(FrameType.CONSUME),
            ConcurrentStableFrozenDict({"request_id": "r", "messages": [_meta(length=5)]}),
            b"ab",
        ),
    )
    with pytest.raises(MsgClientError, match="长度与元数据不一致") as captured:
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _consume())
    assert captured.value.category is ErrorCategory.SERVER_BUG
    assert captured.value.action is ClientAction.FATAL


@pytest.mark.asyncio
async def test_consume_meta_without_length_is_server_bug() -> None:
    """元数据缺整型 `length`：无法切片，判对端装配错误。"""
    server = ScriptedServer()
    server.push(
        "/api/v1/msg/consume",
        raw_content=_frame(
            int(FrameType.CONSUME),
            ConcurrentStableFrozenDict({"request_id": "r", "messages": [_meta()]}),
        ),
    )
    with pytest.raises(MsgClientError, match="缺少整型 length"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _consume())


@pytest.mark.asyncio
async def test_consume_meta_not_mapping_is_server_bug() -> None:
    """元数据不是映射（脏元素）：同样判对端装配错误，不静默跳过（跳过会让消息体错位）。"""
    server = ScriptedServer()
    server.push(
        "/api/v1/msg/consume",
        raw_content=_frame(
            int(FrameType.CONSUME),
            ConcurrentStableFrozenDict({"request_id": "r", "messages": ["junk"]}),
        ),
    )
    with pytest.raises(MsgClientError, match="缺少整型 length"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _consume())


@pytest.mark.asyncio
async def test_error_frame_detail_and_retry_after() -> None:
    """错误帧：`detail` 变 `data`（改投所需 `leader` / `epoch` 在此）、`retry_after_ms` 取帧头。"""
    server = ScriptedServer()
    server.push("/msg/publish", code=350033, data={"leader": "msg-2", "epoch": 4}, retry_after_ms=150)
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())
    assert outcome.code == 350033
    assert outcome.data.get("leader") == "msg-2"
    assert outcome.data.get("epoch") == 4
    assert outcome.retry_after_ms == 150


@pytest.mark.asyncio
async def test_error_frame_without_code_is_server_bug() -> None:
    """错误帧缺整型 `code`：判对端装配错误。"""
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        raw_content=_frame(int(FrameType.ERROR), ConcurrentStableFrozenDict({"request_id": "r", "message": "x"})),
    )
    with pytest.raises(MsgClientError, match="错误帧缺少整型 code"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_response_frame_type_mismatch_is_server_bug() -> None:
    """响应帧类型与请求不一致（把 ack 的响应回给 publish）：判对端错误。"""
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        raw_content=_frame(
            int(FrameType.ACK),
            ConcurrentStableFrozenDict({"request_id": "r", "committed_offset": 1}),
        ),
    )
    with pytest.raises(MsgClientError, match="响应帧类型与请求不一致"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_only_first_frame_is_used() -> None:
    """多帧响应：只取第一帧（服务端只会回单帧，多余帧不解析）。"""
    server = ScriptedServer()
    first = _frame(
        int(FrameType.PUBLISH),
        ConcurrentStableFrozenDict({"request_id": "r", "message_id": "m1", "partition": 0, "offset": 1}),
    )
    second = _frame(
        int(FrameType.PUBLISH),
        ConcurrentStableFrozenDict({"request_id": "r", "message_id": "m2", "partition": 0, "offset": 2}),
    )
    server.push("/msg/publish", raw_content=first + second)
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())
    assert outcome.data.get("message_id") == "m1"


@pytest.mark.asyncio
async def test_gateway_json_response_falls_back_to_unified_body() -> None:
    """网关拦截回 JSON 统一响应体：解不出帧就按统一响应体解析，码表分类照旧生效。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_content=json.dumps({"code": 350005, "message": "限流", "data": None}).encode())
    outcome = await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())
    assert outcome.code == 350005
    assert outcome.message == "限流"


@pytest.mark.asyncio
async def test_gateway_text_response_is_server_bug() -> None:
    """网关错误页（既不是帧也不是统一响应体）：判对端不是本服务。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_content=b"<html>bad gateway</html>")
    with pytest.raises(MsgClientError, match="既不是帧也不是统一响应体"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_empty_response_body_is_server_bug() -> None:
    """空响应体（零帧）：同样按「既不是帧也不是统一响应体」处理。"""
    server = ScriptedServer()
    server.push("/msg/publish", raw_content=b"")
    with pytest.raises(MsgClientError, match="既不是帧也不是统一响应体"):
        await build_transport(_config(), server).post(DEFAULT_ENDPOINT, _publish())


@pytest.mark.asyncio
async def test_oversized_payload_rejected_before_sending() -> None:
    """消息体超 1 MiB：编码期就拒（`350006` / 参数错误 / 不重试），且一个请求都没发。"""
    server = ScriptedServer()
    transport = build_transport(_config(), server)
    with pytest.raises(MsgClientError) as captured:
        await transport.post(DEFAULT_ENDPOINT, _publish(b"x" * (1024 * 1024 + 1)))
    assert captured.value.code == 350006
    assert captured.value.category is ErrorCategory.PARAM_ERROR
    assert captured.value.action is ClientAction.FATAL
    assert captured.value.outcome_unknown is False
    assert len(server.requests) == 0


@pytest.mark.asyncio
async def test_member_endpoints_use_frame_not_json() -> None:
    """成员三端点也走帧（03-6-2）：帧通道不再委托 JSON，请求媒体类型就是帧。"""
    from ._support import build_consumer

    server = ScriptedServer()
    server.push("/api/v1/msg/join", data={"group": "g1", "topic": "orders", "consumer_id": "c1", "partitions": [0]})
    server.push("/api/v1/msg/leave", data={"group": "g1", "topic": "orders", "consumer_id": "c1", "state": "empty"})
    consumer, _ = build_consumer(_config(), server)
    await consumer.join()
    request = server.requests[0]
    assert request.url.path == "/api/v1/msg/join"
    assert request.headers["content-type"].startswith(FRAME_CONTENT_TYPE)
    await consumer.close()


def test_factory_builds_json_transport_for_json_channel() -> None:
    """工厂按通道选实现：`channel=json` 得到 JSON 实现。"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    transport = build_channel_transport(build_config(channel=TransportChannel.JSON), client=client)
    assert isinstance(transport, JsonTransport)


def test_factory_builds_frame_transport_by_default() -> None:
    """工厂缺省给帧实现（换帧后默认形态）。"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    assert isinstance(build_channel_transport(build_config(), client=client), FrameTransport)
