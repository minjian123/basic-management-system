"""03-6 / 03-6-1 用例公共件：按通道参数化的假服务端、配置构造与端到端装配。

设计取舍：

- **不用真实网络**：`httpx.MockTransport` 接管，请求仍走真实传输层（含请求头组装、编解码、异常翻译），
  只把「对端」换掉；
- **假服务端与通道无关**：用例只写「这个端点回什么业务数据」，由本模块按**请求形态**决定回帧还是回 JSON，
  于是同一份用例天然跑通两条通道；
- **请求侧读取也通道无关**：`fields()` / `payload()` 把「请求体」与「帧头 + payload 段」抹平成同一视图，
  断言不用分叉；
- **时钟与抖动复用既有替身**：`msgclient_support.rpc_retry` 的 `FakeClock` / `FixedJitter` 已实现基座
  `Clock` / `JitterSource` 协议，退避与幂等过期都能精确断言，不真等。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import cast

import httpx
import pytest
from msgclient_support.rpc_retry import FakeClock, FixedJitter

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.msgclient.frame import (
    FRAME_CONTENT_TYPE,
    PROTOCOL_VERSION,
    FrameFlags,
    FrameType,
    decode_frames,
    encode_frame,
)
from bms_core.msgclient.messaging import (
    ClientStats,
    MessagingConfig,
    MessagingTransport,
    MsgConsumer,
    MsgProducer,
    TransportChannel,
)
from bms_core.msgclient.messaging.transport import to_wire
from bms_core.msgclient.messaging.transport_factory import build_transport as build_channel_transport
from bms_core.msgclient.retry import Clock, JitterMode, RetryPolicy

__all__ = [
    "DEFAULT_ENDPOINT",
    "Reply",
    "ScriptedServer",
    "build_config",
    "build_consumer",
    "build_producer",
    "build_transport",
    "channels",
]

DEFAULT_ENDPOINT = "http://msg-1:8000"
"""用例缺省地址。"""

channels = (TransportChannel.FRAME, TransportChannel.JSON)
"""参数化用的两条通道（顺序固定：帧在前，失败时先看默认形态）。"""


@pytest.fixture(params=channels)
def channel(request: pytest.FixtureRequest) -> TransportChannel:
    """通道参数化夹具：声明 `channel` 参数的用例在两条通道上各跑一遍。

    Args:
        request: pytest 夹具请求（`param` 是本次的通道）。

    Returns:
        TransportChannel: 本次运行的通道。
    """
    value = request.param
    assert isinstance(value, TransportChannel)
    return value


def _empty_headers() -> ConcurrentStableFrozenDict[str, str]:
    """新建空响应头。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 空映射。
    """
    return ConcurrentStableFrozenDict()


def _empty_payloads() -> ConcurrentStableFrozenList[bytes]:
    """新建空消息体列表。

    Returns:
        ConcurrentStableFrozenList[bytes]: 空列表。
    """
    return ConcurrentStableFrozenList()


@dataclass
class Reply:
    """一条脚本化响应（通道无关：由假服务端按请求形态编码）。

    Attributes:
        path: 命中路径（`/msg/publish` 等）。
        code: 产品码（0 = 成功）。
        data: 业务数据（成功时是结果、失败时是异常随附数据）。
        payloads: 拉取结果里各条消息体的原始字节（缺省 = 与 `data["messages"]` 等长的空体）。
        detail: 错误帧 / 错误体里的随附数据（缺省取 `data`）。
        message: 提示。
        retry_after_ms: 建议重试间隔（帧头字段）。
        status: HTTP 状态码。
        headers: 响应头。
        error: 若给出则直接抛出（模拟传输层异常）。
        raw_text: 裸文本响应体（覆盖「不是 JSON / 不是帧」的分支）。
        raw_content: 裸字节响应体（构造畸形帧等）。
    """

    path: str
    code: int = 0
    data: object | None = None
    payloads: ConcurrentStableFrozenList[bytes] = field(default_factory=_empty_payloads)
    detail: object | None = None
    message: str = ""
    retry_after_ms: int | None = None
    status: int = 200
    headers: ConcurrentStableFrozenDict[str, str] = field(default_factory=_empty_headers)
    error: Exception | None = None
    raw_text: str | None = None
    raw_content: bytes | None = None


def _is_frame_request(request: httpx.Request) -> bool:
    """请求是否为帧形态（只看媒体类型，与服务端判定一致）。

    Args:
        request: 请求。

    Returns:
        bool: 帧形态为 True。
    """
    raw = request.headers.get("content-type", "")
    return raw.split(";")[0].strip().lower() == FRAME_CONTENT_TYPE


def _segments(reply: Reply, count: int) -> ConcurrentStableFrozenList[bytes]:
    """取脚本化的消息体切片（缺省补空体）。

    Args:
        reply: 脚本响应。
        count: `data["messages"]` 的条数。

    Returns:
        ConcurrentStableFrozenList[bytes]: 逐条消息体。
    """
    if reply.payloads:
        return reply.payloads
    return ConcurrentStableFrozenList([b""] * count)


def _messages_of(data: object) -> ConcurrentStableFrozenList[object]:
    """从脚本数据里取 `messages` 数组（非数组返回空）。

    Args:
        data: 脚本数据。

    Returns:
        ConcurrentStableFrozenList[object]: 元素列表。
    """
    if not isinstance(data, Mapping):
        return ConcurrentStableFrozenList()
    raw = cast("Mapping[str, object]", data).get("messages")
    if not isinstance(raw, list):
        return ConcurrentStableFrozenList()
    return ConcurrentStableFrozenList(cast("list[object]", raw))


def _as_mapping(value: object) -> ConcurrentStableFrozenDict[str, object]:
    """把脚本数据当映射读（非映射给空映射）。

    Args:
        value: 脚本数据。

    Returns:
        ConcurrentStableFrozenDict[str, object]: 数据映射。
    """
    if not isinstance(value, Mapping):
        return ConcurrentStableFrozenDict()
    mapping = cast("Mapping[str, object]", value)
    return ConcurrentStableFrozenDict({str(key): item for key, item in mapping.items()})


def _json_body(reply: Reply) -> object:
    """把脚本响应编成 JSON 统一响应体（消息体转 base64）。

    Args:
        reply: 脚本响应。

    Returns:
        object: 响应体（内置结构）。
    """
    mapping = _as_mapping(reply.data)
    data: object = reply.data
    if "messages" in mapping:
        messages = _messages_of(mapping)
        segments = _segments(reply, len(messages))
        merged: list[object] = []  # bare-collections:allow（JSON 序列化边界）
        for index, item in enumerate(messages):
            if isinstance(item, Mapping):
                encoded = base64.b64encode(segments[index]).decode("ascii")
                merged.append({**cast("Mapping[str, object]", item), "payload": encoded})
            else:
                merged.append(item)
        data = {**mapping, "messages": merged}
    payload_data = (reply.detail if reply.detail is not None else reply.data) if reply.code else data
    return {"code": reply.code, "message": reply.message, "data": payload_data}


def _frame_body(reply: Reply, request_frame_type: int, request_id: object) -> bytes:
    """把脚本响应编成一帧（结果帧或错误帧）。

    Args:
        reply: 脚本响应。
        request_frame_type: 请求帧类型（结果帧沿用）。
        request_id: 请求标识（回显）。

    Returns:
        bytes: 帧字节。
    """
    if reply.code != 0:
        detail = reply.data if reply.detail is None else reply.detail
        failure: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "request_id": request_id,
                "protocol_version": PROTOCOL_VERSION,
                "code": reply.code,
                "message": reply.message,
                "retryable": False,
                "layer": "business",
                "category": "business_reject",
                "detail": detail,
                "retry_after_ms": reply.retry_after_ms,
            }
        )
        return encode_frame(frame_type=int(FrameType.ERROR), flags=FrameFlags.RESPONSE, header=failure)
    header: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"request_id": request_id, "protocol_version": PROTOCOL_VERSION}
    )
    mapping = _as_mapping(reply.data)
    payload = b""
    if request_frame_type == int(FrameType.PUBLISH):
        for name in ("message_id", "log_id", "topic", "partition", "offset", "deliver_at"):
            header.set(name, mapping.get(name))
    elif request_frame_type == int(FrameType.CONSUME):
        messages = _messages_of(mapping)
        segments = _segments(reply, len(messages))
        metas: list[object] = []  # bare-collections:allow（帧头是 MessagePack Map 的序列化边界）
        for index, item in enumerate(messages):
            if isinstance(item, Mapping):
                metas.append({**cast("Mapping[str, object]", item), "length": len(segments[index])})
            else:
                metas.append(item)
        header.set("count", len(metas))
        header.set("messages", metas)
        header.set("paused", bool(mapping.get("paused")))
        header.set("inflight_messages", mapping.get("inflight_messages", 0))
        header.set("inflight_bytes", mapping.get("inflight_bytes", 0))
        payload = b"".join(segments)
    else:
        header.set("committed_offset", mapping.get("committed_offset", 0))
    return encode_frame(frame_type=request_frame_type, flags=FrameFlags.RESPONSE, header=header, payload=payload)


class ScriptedServer:
    """按路径排队响应的假服务端（按请求形态回帧或回 JSON，并记录收到的请求）。

    Attributes:
        replies: 待消费的脚本响应。
        requests: 收到的请求（按到达顺序）。
    """

    def __init__(self) -> None:
        """初始化空脚本。"""
        self.replies: ConcurrentStableList[Reply] = ConcurrentStableList()
        self.requests: ConcurrentStableList[httpx.Request] = ConcurrentStableList()

    def push(
        self,
        path: str,
        *,
        code: int = 0,
        data: object | None = None,
        payloads: ConcurrentStableFrozenList[bytes] | None = None,
        detail: object | None = None,
        message: str = "",
        retry_after_ms: int | None = None,
        status: int = 200,
        headers: ConcurrentStableFrozenDict[str, str] | None = None,
        error: Exception | None = None,
        raw_text: str | None = None,
        raw_content: bytes | None = None,
    ) -> None:
        """排一条响应（按加入顺序消费）。

        Args:
            path: 命中路径。
            code: 产品码（0 = 成功）。
            data: 业务数据。
            payloads: 拉取结果里各条消息体。
            detail: 错误随附数据（缺省取 `data`）。
            message: 提示。
            retry_after_ms: 建议重试间隔（帧头字段）。
            status: HTTP 状态码。
            headers: 响应头。
            error: 要抛出的异常。
            raw_text: 裸文本响应体。
            raw_content: 裸字节响应体。
        """
        self.replies.add(
            Reply(
                path=path,
                code=code,
                data=to_wire(data),
                payloads=payloads if payloads is not None else _empty_payloads(),
                detail=to_wire(detail),
                message=message,
                retry_after_ms=retry_after_ms,
                status=status,
                headers=headers if headers is not None else _empty_headers(),
                error=error,
                raw_text=raw_text,
                raw_content=raw_content,
            )
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        """httpx.MockTransport 的处理函数：按路径取第一条匹配脚本并按请求形态编码。

        Args:
            request: 请求。

        Returns:
            httpx.Response: 脚本化响应。

        Raises:
            Exception: 脚本指定的异常（原样抛出）。
        """
        self.requests.add(request)
        for index in range(len(self.replies)):
            reply = self.replies[index]
            if reply.path != request.url.path:
                continue
            self.replies.pop(index)
            if reply.error is not None:
                raise reply.error
            return self._render(reply, request)
        return httpx.Response(404, json={"code": 404, "message": "未脚本化", "data": None})

    def _render(self, reply: Reply, request: httpx.Request) -> httpx.Response:
        """按请求形态把脚本响应渲染成帧或 JSON。

        Args:
            reply: 脚本响应。
            request: 请求。

        Returns:
            httpx.Response: 响应。
        """
        headers = {key: value for key, value in reply.headers.items()}
        if not _is_frame_request(request):
            if reply.raw_text is not None:
                return httpx.Response(reply.status, text=reply.raw_text, headers=headers)
            return httpx.Response(reply.status, json=_json_body(reply), headers=headers)
        if reply.raw_content is not None:
            raw_headers = {**headers, "content-type": FRAME_CONTENT_TYPE}
            return httpx.Response(reply.status, content=reply.raw_content, headers=raw_headers)
        frames = decode_frames(request.content).frames
        request_id = frames[0].header.get("request_id") if frames else None
        content = _frame_body(reply, frames[0].frame_type if frames else int(FrameType.PUBLISH), request_id)
        return httpx.Response(reply.status, content=content, headers={**headers, "content-type": FRAME_CONTENT_TYPE})

    def fields(self, index: int = 0) -> ConcurrentStableFrozenDict[str, object]:
        """取第 `index` 个请求的业务字段（JSON 取请求体、帧取帧头，均去掉传输层字段）。

        Args:
            index: 请求序号。

        Returns:
            ConcurrentStableFrozenDict[str, object]: 业务字段（只读视图，用例按需取值断言）。
        """
        request = self.requests[index]
        if _is_frame_request(request):
            frames = decode_frames(request.content).frames
            header = frames[0].header if frames else ConcurrentStableDict[str, object]()
            return ConcurrentStableFrozenDict({key: value for key, value in header.items() if key != "request_id"})
        body = json.loads(request.content)  # 内置结构（用例断言的序列化边界）
        mapping = cast("dict[str, object]", body)
        return ConcurrentStableFrozenDict({str(key): value for key, value in mapping.items() if key != "payload"})

    def payload(self, index: int = 0) -> bytes:
        """取第 `index` 个请求的消息体原始字节（JSON 解 base64、帧取 payload 段）。

        Args:
            index: 请求序号。

        Returns:
            bytes: 消息体字节。
        """
        request = self.requests[index]
        if _is_frame_request(request):
            frames = decode_frames(request.content).frames
            return bytes(frames[0].payload) if frames else b""
        body = cast("dict[str, object]", json.loads(request.content))  # bare-collections:allow（同上）
        encoded = body.get("payload")
        return base64.b64decode(str(encoded)) if encoded else b""

    def request_paths(self) -> ConcurrentStableFrozenList[str]:
        """取所有请求的路径（按到达顺序）。

        Returns:
            ConcurrentStableFrozenList[str]: 路径列表。
        """
        return ConcurrentStableFrozenList([request.url.path for request in self.requests])


def build_config(*, clock: Clock | None = None, **overrides: object) -> MessagingConfig:
    """构造一个可用配置（缺省单地址、单租户、两次重试、无抖动）。

    Args:
        clock: 注入的时钟（缺省新建）。
        overrides: 覆盖字段（用例只改少量字段，含 `channel`）。

    Returns:
        MessagingConfig: 配置。
    """
    base = MessagingConfig(
        endpoints=ConcurrentStableFrozenList([DEFAULT_ENDPOINT]),
        tenant="t1",
        retry=RetryPolicy(max_retries=2, base_ms=100, multiplier=2, cap_ms=2_000, jitter=JitterMode.NONE),
        clock=clock if clock is not None else FakeClock(),
        jitter=FixedJitter([1]),
    )
    if not overrides:
        return base
    return replace(base, **overrides)


def build_transport(config: MessagingConfig, server: ScriptedServer) -> MessagingTransport:
    """构造接在假服务端上的传输层（实现由 `config.channel` 决定）。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        MessagingTransport: 传输层。
    """
    client = httpx.AsyncClient(transport=httpx.MockTransport(server.handler))
    return build_channel_transport(config, client=client)


def build_producer(config: MessagingConfig, server: ScriptedServer) -> tuple[MsgProducer, ClientStats]:
    """构造生产端与它的计数器。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        tuple[MsgProducer, ClientStats]: （生产端，计数器）。
    """
    stats = ClientStats()
    return MsgProducer(config, build_transport(config, server), stats), stats


def build_consumer(config: MessagingConfig, server: ScriptedServer) -> tuple[MsgConsumer, ClientStats]:
    """构造消费端与它的计数器。

    Args:
        config: 配置。
        server: 假服务端。

    Returns:
        tuple[MsgConsumer, ClientStats]: （消费端，计数器）。
    """
    stats = ClientStats()
    consumer = MsgConsumer(
        config,
        build_transport(config, server),
        stats,
        group="g1",
        namespace="ns",
        topic="orders",
        consumer_id="c1",
    )
    return consumer, stats
