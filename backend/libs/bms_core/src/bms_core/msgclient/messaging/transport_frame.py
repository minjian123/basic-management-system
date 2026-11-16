"""帧承载（03-6-1）：业务字段进帧头、消息体走 payload 段、响应从帧头还原。

**三条从服务端实现里读出来的硬约束**（别在实现里漂）：

1. **帧头不放消息体**：`msg` 仓闸门见到 `payload` 键直接判 `350018`，消息体只能进 payload 段；
2. **`request_id` 必填**：缺键是协议层 `350018`，所以本层每帧现生成一个；
3. **拉取的消息体是按序拼接的**：`header.messages[i].length` 是切分表，按长度切片即可，不做整包重排。

**全部业务端点一律走帧**（03-6-2 起）：`ApiRequest.frame_type` 必填，本层不再有「某端点没有帧形态、
交给 JSON 实现」的分支——成员三端点（加入 / 离开 / 成员心跳）已由服务端登记类型 7 / 8 / 9。

**请求是帧不代表响应一定是帧**：请求可能在到达服务前被反代拒掉（429 / 502），此时响应不是帧——先按帧
解码，解不出再按统一响应体解析，两者都不成立才判「对端不是本服务」。这是**响应侧兜底**，与已删除的
「请求侧委托」不是一回事。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import uuid4

import httpx

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.msgclient.errors import ErrorCategory, MsgError
from bms_core.msgclient.frame import (
    FRAME_CONTENT_TYPE,
    Frame,
    FrameFlags,
    FrameType,
    decode_frames,
    encode_frame,
)
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.errors import CLIENT_ERROR_CODE, ClientAction, MsgClientError
from bms_core.msgclient.messaging.transport import (
    ApiOutcome,
    ApiRequest,
    HttpxChannel,
    freeze_data,
    to_wire,
)
from bms_core.msgclient.retry import parse_retry_after

__all__ = ["FrameTransport"]

_NOT_FRAME_HINT = "响应既不是帧也不是统一响应体"
"""两条解析路径都不成立时的提示（网关改写 / 对端不是本服务）。"""

_ERROR_FRAME_TYPE = int(FrameType.ERROR)
"""错误帧类型（服务端把业务错误也放在 200 的帧里，见 03-2 §6.5）。"""

_PUBLISH_KEYS = ("message_id", "log_id", "topic", "partition", "offset", "deliver_at")
"""发布回执的帧头键（与 `PublishResult` 同名，客户端按同名字段取）。"""

_MEMBER_KEYS = (
    "group",
    "topic",
    "consumer_id",
    "generation",
    "state",
    "partitions",
    "member_count",
    "heartbeat_interval_ms",
    "session_timeout_ms",
)
"""成员分配的帧头键（与 `Assignment` 同名；`partitions` 是整数列表，服务端平铺下发）。"""

_LEAVE_KEYS = ("group", "topic", "consumer_id", "generation", "state")
"""离开结果的帧头键（与 `LeaveResult` 同名；客户端只用于排障，不参与状态判定）。"""


def _as_int(value: object) -> int:
    """把帧头字段转成整数（非整数按 0，避免把 `None` 漏进业务模型）。

    Args:
        value: 帧头字段值。

    Returns:
        int: 整数或 0。
    """
    return value if isinstance(value, int) else 0


def _header_retry_after(response: httpx.Response) -> int | None:
    """取 HTTP `Retry-After`（只认 delta-seconds，转毫秒）。

    Args:
        response: HTTP 响应。

    Returns:
        int | None: 毫秒；无该头则 None。
    """
    return parse_retry_after(tuple(response.headers.items()))


def _lengths(items: ConcurrentStableFrozenList[object]) -> ConcurrentStableList[int]:
    """取每条消息的 `length`（切分表；缺失或非整数即装配错误）。

    Args:
        items: 帧头 `messages` 列表。

    Returns:
        ConcurrentStableList[int]: 各条消息体长度。

    Raises:
        MsgClientError: 元数据不是映射、或缺整型 `length`（对端装配坏了，重试无意义）。
    """
    lengths: ConcurrentStableList[int] = ConcurrentStableList()
    for item in items:
        length = cast("Mapping[str, object]", item).get("length") if isinstance(item, Mapping) else None
        if not isinstance(length, int):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message="帧内消息元数据缺少整型 length",
            )
        lengths.add(length)
    return lengths


def _consume_data(
    header: Mapping[str, object],  # bare-collections:allow（基座帧头是只读视图，此处不新建集合）
    payload: bytes,
) -> tuple[ConcurrentStableFrozenDict[str, object], ConcurrentStableFrozenList[bytes]]:
    """把拉取结果帧拆成「业务数据 + 逐条消息体」。

    Args:
        header: 结果帧头。
        payload: 结果帧 payload（各消息体按序拼接）。

    Returns:
        tuple[ConcurrentStableFrozenDict[str, object], ConcurrentStableFrozenList[bytes]]:
        （业务数据，逐条消息体）。

    Raises:
        MsgClientError: 元数据合计长度与 payload 总长不符（对端装配坏了）。
    """
    raw_messages = header.get("messages")
    items: ConcurrentStableFrozenList[object] = (
        ConcurrentStableFrozenList(cast("list[object]", raw_messages))
        if isinstance(raw_messages, list)
        else ConcurrentStableFrozenList()
    )
    lengths = _lengths(items)
    total = sum(lengths)
    if total != len(payload):
        raise MsgClientError(
            code=CLIENT_ERROR_CODE,
            category=ErrorCategory.SERVER_BUG,
            action=ClientAction.FATAL,
            message=f"帧内消息体长度与元数据不一致（元数据合计 {total}，实际 {len(payload)}）",
        )
    segments: ConcurrentStableList[bytes] = ConcurrentStableList()
    cursor = 0
    for length in lengths:
        segments.add(payload[cursor : cursor + length])
        cursor += length
    data: ConcurrentStableFrozenDict[str, object] = ConcurrentStableFrozenDict(
        {
            "count": len(items),
            "messages": [to_wire(item) for item in items],
            "paused": bool(header.get("paused")),
            "inflight_messages": _as_int(header.get("inflight_messages")),
            "inflight_bytes": _as_int(header.get("inflight_bytes")),
        }
    )
    return data, ConcurrentStableFrozenList(segments)


class FrameTransport(HttpxChannel):
    """帧传输（`application/x-msg-frame`）：全部业务端点（数据面四端点 + 成员三端点）一律走帧。

    Attributes:
        config: 客户端配置。
        client: httpx 异步客户端（用例注入 `MockTransport`）。
    """

    def __init__(self, config: MessagingConfig, *, client: httpx.AsyncClient | None = None) -> None:
        """初始化。

        Args:
            config: 客户端配置。
            client: 外部注入的 httpx 客户端（None = 按配置新建）。
        """
        super().__init__(config, client=client)

    async def post(self, endpoint: str, request: ApiRequest) -> ApiOutcome:
        """发一次帧请求并解析响应帧。

        Args:
            endpoint: 服务地址（`scheme://host:port`，不带路径）。
            request: 业务请求。

        Returns:
            ApiOutcome: 解析结果。

        Raises:
            MsgClientError: 请求无法编码 / 传输失败 / 响应既不是帧也不是统一响应体。
        """
        frame = self._encode(request)
        headers = self.headers()
        headers.set("Content-Type", FRAME_CONTENT_TYPE)
        response = await self._post_bytes(f"{endpoint}{request.path}", frame, headers)
        return self._decode(response, request.frame_type)

    async def close(self) -> None:
        """关闭底层客户端（幂等）。"""

    def _encode(self, request: ApiRequest) -> bytes:
        """把业务请求编成一帧（编码期失败即「请求未发出」）。

        Args:
            request: 业务请求。

        Returns:
            bytes: 完整帧字节。

        Raises:
            MsgClientError: 结构超限 / 版本越界（码取自基座异常，类别为参数错误）。
        """
        header: ConcurrentStableDict[str, object] = ConcurrentStableDict({"request_id": uuid4().hex})
        for key, value in request.fields.items():
            header.set(str(key), to_wire(value))
        try:
            return encode_frame(
                frame_type=request.frame_type,
                header=header,
                flags=FrameFlags.NEED_RESPONSE,
                payload=request.payload,
            )
        except MsgError as exc:
            raise MsgClientError(
                code=exc.code,
                category=ErrorCategory.PARAM_ERROR,
                action=ClientAction.FATAL,
                message=f"请求无法编码成帧：{exc}",
            ) from exc

    def _decode(self, response: httpx.Response, frame_type: int) -> ApiOutcome:
        """解析响应（帧优先，解不出再按统一响应体兜底）。

        Args:
            response: HTTP 响应。
            frame_type: 请求帧类型（用于校验与还原）。

        Returns:
            ApiOutcome: 解析结果。

        Raises:
            MsgClientError: 响应不可解析。
        """
        try:
            batch = decode_frames(response.content)
        except MsgError:
            return self._parse_json(response, hint=_NOT_FRAME_HINT)
        if not batch.frames:
            return self._parse_json(response, hint=_NOT_FRAME_HINT)
        frame = batch.frames[0]
        if frame.frame_type == _ERROR_FRAME_TYPE:
            return self._error(frame, response)
        if frame.frame_type != frame_type:
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message=f"响应帧类型与请求不一致（请求 {frame_type}，响应 {frame.frame_type}）",
            )
        return self._result(frame, frame_type)

    @staticmethod
    def _error(frame: Frame, response: httpx.Response) -> ApiOutcome:
        """把错误帧还原成 `ApiOutcome`（`detail` → `data`，`retry_after_ms` → 建议间隔）。

        Args:
            frame: 错误帧。
            response: HTTP 响应（兜底取 `Retry-After`）。

        Returns:
            ApiOutcome: `code != 0` 的结果。

        Raises:
            MsgClientError: 错误帧缺整型 `code`（对端装配坏了）。
        """
        code = frame.header.get("code")
        if not isinstance(code, int):
            raise MsgClientError(
                code=CLIENT_ERROR_CODE,
                category=ErrorCategory.SERVER_BUG,
                action=ClientAction.FATAL,
                message="错误帧缺少整型 code",
            )
        message = frame.header.get("message")
        retry_after = frame.header.get("retry_after_ms")
        return ApiOutcome(
            code=code,
            message="" if message is None else str(message),
            data=freeze_data(frame.header.get("detail")),
            retry_after_ms=retry_after if isinstance(retry_after, int) else _header_retry_after(response),
        )

    @staticmethod
    def _result(frame: Frame, frame_type: int) -> ApiOutcome:
        """把结果帧还原成 `ApiOutcome`（按请求帧类型分派）。

        Args:
            frame: 结果帧。
            frame_type: 请求帧类型。

        Returns:
            ApiOutcome: `code = 0` 的结果。
        """
        header = frame.header
        if frame_type == int(FrameType.PUBLISH):
            data: ConcurrentStableFrozenDict[str, object] = ConcurrentStableFrozenDict(
                {name: header.get(name) for name in _PUBLISH_KEYS}
            )
            return ApiOutcome(code=0, message="", data=data)
        if frame_type == int(FrameType.CONSUME):
            data, segments = _consume_data(header, bytes(frame.payload))
            return ApiOutcome(code=0, message="", data=data, payload_segments=segments)
        if frame_type in (int(FrameType.JOIN), int(FrameType.MEMBER_HEARTBEAT)):
            # 加入与成员心跳返回同一份分配（`MemberAssignment`）：帧头九键与 `Assignment` 同名，直接透传。
            return ApiOutcome(
                code=0,
                message="",
                data=ConcurrentStableFrozenDict({name: header.get(name) for name in _MEMBER_KEYS}),
            )
        if frame_type == int(FrameType.LEAVE):
            return ApiOutcome(
                code=0,
                message="",
                data=ConcurrentStableFrozenDict({name: header.get(name) for name in _LEAVE_KEYS}),
            )
        return ApiOutcome(
            code=0,
            message="",
            data=ConcurrentStableFrozenDict({"committed_offset": header.get("committed_offset")}),
        )
