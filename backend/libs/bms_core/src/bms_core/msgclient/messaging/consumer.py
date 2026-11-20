"""消息消费端（msg 03-6 详细设计 §5.3 / §6.3 / §6.4）：拉取循环 + 成员保活。

**边界（写死在这里）**：

- **不做客户端再均衡**：分配由服务端主导，本类只跟随 `partitions` 与 `generation`；
- **不做位点回退**：数据面 `commit` 单调前进，回退只有管理面（`msg:manage`），本类不封装；
- **心跳间隔取服务端返回值**（缺省 10s → 客户端 6s），不自造间隔——自造会与服务端
  `session_timeout_ms` 打架，成员被判定超时后分区易主，反而拉不到消息。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from dataclasses import dataclass, field
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.roots import BaseFrameworkObject, BaseValueObject
from bms_core.msgclient.frame import FrameType
from bms_core.msgclient.messaging.codes import rule_for_consume
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.errors import ClientAction, MsgClientError
from bms_core.msgclient.messaging.stats import ClientStats
from bms_core.msgclient.messaging.transport import ApiOutcome, ApiRequest, MessagingTransport

__all__ = [
    "Assignment",
    "CommitResult",
    "MsgConsumer",
    "PollResult",
    "ReceivedMessage",
]

JOIN_PATH = "/api/v1/msg/join"
"""加入消费组（服务端主导分配；统一 JSON 响应，与 msg 0712 起的成员端点一致）。"""

HEARTBEAT_PATH = "/api/v1/msg/heartbeat"
"""成员心跳（顺带清理同组超时成员、必要时重算分配；与连接心跳是两件事）。"""

LEAVE_PATH = "/api/v1/msg/leave"
"""离开消费组（幂等）。"""

CONSUME_PATH = "/api/v1/msg/consume"
"""拉取一批消息（成员制：分区必须在该成员分配内）。"""

ACK_PATH = "/api/v1/msg/ack"
"""确认一条消息（位点前进）。"""

NACK_PATH = "/api/v1/msg/nack"
"""拒绝一条消息（转死信 + 位点前移）。"""

MAX_FETCH_MESSAGES = 100
"""单次拉取条数上限（与服务端 `MAX_FETCH_MESSAGES` 同值）。"""

MAX_WAIT_LIMIT_MS = 60_000
"""长轮询上限（与服务端 `SUBSCRIBE_MAX_WAIT_LIMIT_MS` 同值）。"""

_HEARTBEAT_INTERVAL_RATIO = 0.6
"""心跳间隔占服务端间隔的比例（留抖动余量，避免卡在会话超时边界）。"""

_MIN_HEARTBEAT_INTERVAL_MS = 1_000
"""心跳间隔下限（服务端给得再小也不低于 1 秒，避免打成紧循环）。"""


def _empty_partitions() -> ConcurrentStableFrozenList[int]:
    """新建空分配。

    Returns:
        ConcurrentStableFrozenList[int]: 空列表。
    """
    return ConcurrentStableFrozenList()


def _empty_messages() -> ConcurrentStableFrozenList[ReceivedMessage]:
    """新建空消息列表。

    Returns:
        ConcurrentStableFrozenList[ReceivedMessage]: 空列表。
    """
    return ConcurrentStableFrozenList()


def _empty_headers() -> ConcurrentStableFrozenDict[str, str]:
    """新建空头映射。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 空映射。
    """
    return ConcurrentStableFrozenDict()


@dataclass(frozen=True)
class Assignment(BaseValueObject):
    """成员分配（`join` / `heartbeat` 的返回）。

    Attributes:
        group: 消费组。
        topic: 主题名。
        consumer_id: 成员标识。
        generation: 世代（变了即分配变化）。
        state: 组状态（`stable` / `empty` 等）。
        partitions: 本成员负责的分区号。
        member_count: 组内成员数。
        heartbeat_interval_ms: 服务端要求的心跳间隔（毫秒）。
        session_timeout_ms: 会话超时（毫秒）。
    """

    group: str
    topic: str
    consumer_id: str
    generation: int = 0
    state: str = ""
    partitions: ConcurrentStableFrozenList[int] = field(default_factory=_empty_partitions)
    member_count: int = 0
    heartbeat_interval_ms: int = 10_000
    session_timeout_ms: int = 30_000


@dataclass(frozen=True)
class ReceivedMessage(BaseValueObject):
    """拉取到的一条消息（`payload` 已从 base64 解成原始字节）。

    Attributes:
        message_id: 消息 ID（重投不变）。
        topic: 主题名。
        partition: 分区号。
        offset: 分区内序号。
        key: 分区键（可空）。
        payload: 消息体原始字节。
        headers: 结构化头。
        delivery_count: 投递次数（首次 1，重投递增）。
        published_at: 发布时间（服务端原样文本）。
        content_type: 内容类型。
        compression: 压缩算法（`none` 表示未压缩）。
        uncompressed_len: 解压后字节数（可空）。
        trace_id: 链路标识（可空）。
        span_id: 跨度标识（可空）。
        trace_flags: 采样标记（可空）。
    """

    message_id: str
    topic: str
    partition: int
    offset: int
    payload: bytes = b""
    key: str | None = None
    headers: ConcurrentStableFrozenDict[str, str] = field(default_factory=_empty_headers)
    delivery_count: int = 1
    published_at: str = ""
    content_type: str = ""
    compression: str = "none"
    uncompressed_len: int | None = None
    trace_id: str | None = None
    span_id: str | None = None
    trace_flags: str | None = None


@dataclass(frozen=True)
class PollResult(BaseValueObject):
    """一次拉取的结果。

    Attributes:
        messages: 本次投递的消息。
        partition: 本次拉取的分区号。
        paused: 是否因在途达阈值而暂停（不是错误）。
        inflight_messages: 本分区当前在途条数。
        inflight_bytes: 本分区当前在途字节合计。
    """

    messages: ConcurrentStableFrozenList[ReceivedMessage] = field(default_factory=_empty_messages)
    partition: int = 0
    paused: bool = False
    inflight_messages: int = 0
    inflight_bytes: int = 0


@dataclass(frozen=True)
class CommitResult(BaseValueObject):
    """确认 / 拒绝的结果。

    Attributes:
        committed_offset: 已提交位点（已处理完的最后一条 + 1）。
    """

    committed_offset: int = 0


def _as_int(value: object, default: int = 0) -> int:
    """把响应字段转成整数（非整数返回缺省值）。

    Args:
        value: 字段值。
        default: 缺省值。

    Returns:
        int: 整数。
    """
    return value if isinstance(value, int) else default


def _as_optional_int(value: object) -> int | None:
    """把响应字段转成可选整数（非整数返回 None）。

    Args:
        value: 字段值。

    Returns:
        int | None: 整数或 None。
    """
    return value if isinstance(value, int) else None


def _headers_of(value: object) -> ConcurrentStableFrozenDict[str, str]:
    """把响应里的 `headers` 转成不可变字符串映射（非对象返回空）。

    Args:
        value: 字段值。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 头映射。
    """
    if not isinstance(value, dict):
        return ConcurrentStableFrozenDict()
    mapping = cast("dict[str, object]", value)
    return ConcurrentStableFrozenDict({str(key): str(item) for key, item in mapping.items()})


def _items(value: object) -> ConcurrentStableFrozenList[object]:
    """把响应里的数组字段转成不可变对象列表（非数组返回空）。

    **为什么要这一层**：响应是 `dict[str, object]`，直接 `isinstance(x, list)` 会让元素类型退化成
    `Unknown`，后面每个字段都要再 cast 一次；这里一次收敛成 `object`，下游按字段各自判型。

    Args:
        value: 字段值。

    Returns:
        ConcurrentStableFrozenList[object]: 元素列表。
    """
    if not isinstance(value, list):
        return ConcurrentStableFrozenList()
    return ConcurrentStableFrozenList(cast("list[object]", value))


class MsgConsumer(BaseFrameworkObject):
    """消息消费端（一个实例绑定一个组的一个主题；分区由服务端分配）。

    Attributes:
        config: 客户端配置。
        transport: 传输层。
        stats: 客户端计数器。
        group: 消费组。
        namespace: 命名空间。
        topic: 主题名。
        consumer_id: 成员标识。
    """

    def __init__(
        self,
        config: MessagingConfig,
        transport: MessagingTransport,
        stats: ClientStats,
        *,
        group: str,
        namespace: str,
        topic: str,
        consumer_id: str,
    ) -> None:
        """初始化（不加入组，`join()` 才加入）。

        Args:
            config: 客户端配置。
            transport: 传输层。
            stats: 客户端计数器。
            group: 消费组。
            namespace: 命名空间。
            topic: 主题名。
            consumer_id: 成员标识。
        """
        self.config = config
        self.transport = transport
        self.stats = stats
        self.group = group
        self.namespace = namespace
        self.topic = topic
        self.consumer_id = consumer_id
        self._assignment: Assignment | None = None
        self._cursor = 0
        self._endpoint_cursor = 0
        self._closed = False
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def assignment(self) -> Assignment | None:
        """当前分配（未加入为 None）。

        Returns:
            Assignment | None: 分配。
        """
        return self._assignment

    async def join(self) -> Assignment:
        """加入消费组（服务端主导分配）；首次加入后启动心跳任务。

        Returns:
            Assignment: 分配。

        Raises:
            ParamError: 客户端已关闭。
            MsgClientError: 服务端拒绝（主题不存在 / 配额 / 成员类）。
        """
        self._ensure_open()
        outcome = await self._request(JOIN_PATH, frame_type=int(FrameType.JOIN), fields=self._member_fields())
        assignment = self._assignment_of(outcome.data)
        self._assignment = assignment
        self._cursor = 0
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self.stats.incr("join_total")
        return assignment

    async def poll(self, *, max_messages: int = 20, max_wait_ms: int = 30_000) -> PollResult:
        """按分配轮转拉取一个分区（成员失效自动重新加入一次）。

        Args:
            max_messages: 本次最多拉取条数（1~100）。
            max_wait_ms: 长轮询挂起上限（0~60000）。

        Returns:
            PollResult: 拉取结果。

        Raises:
            ParamError: 尚未加入组 / 参数越界 / 客户端已关闭。
            MsgClientError: 服务端拒绝（重新加入后仍失败即抛）。
        """
        self._ensure_open()
        if self._assignment is None or not self._assignment.partitions:
            raise ParamError("尚未 join 或分配为空：先 join() 再 poll()")
        if not 1 <= max_messages <= MAX_FETCH_MESSAGES:
            raise ParamError(f"max_messages 必须在 1~{MAX_FETCH_MESSAGES}")
        if not 0 <= max_wait_ms <= MAX_WAIT_LIMIT_MS:
            raise ParamError(f"max_wait_ms 必须在 0~{MAX_WAIT_LIMIT_MS}")
        partition = self._next_partition()
        fields: ConcurrentStableDict[str, object] = self._member_fields()
        fields.set("partition", partition)
        fields.set("max_messages", max_messages)
        fields.set("max_wait_ms", max_wait_ms)
        rejoined = False
        while True:
            try:
                outcome = await self._request(CONSUME_PATH, frame_type=int(FrameType.CONSUME), fields=fields)
            except MsgClientError as exc:
                if exc.action is ClientAction.REFRESH and not rejoined:
                    rejoined = True
                    self.stats.incr("rejoin_total")
                    await self.join()
                    # 重新加入后分配可能整体改变，本轮改拉新分配里的下一个分区；
                    # `partition` 同步更新，否则返回结果会带着失效分区的号（排障时会指向错分区）。
                    partition = self._next_partition()
                    fields.set("partition", partition)
                    continue
                raise
            break
        return self._poll_result(outcome, partition)

    async def ack(self, message: ReceivedMessage) -> CommitResult:
        """确认一条消息（位点前进）。

        Args:
            message: 已处理完的消息（自带分区）。

        Returns:
            CommitResult: 已提交位点。

        Raises:
            ParamError: 客户端已关闭。
            MsgClientError: 服务端拒绝（位点非法 / 成员失效 / 已进死信）。
        """
        return await self._settle(ACK_PATH, message, frame_type=int(FrameType.ACK), extra=None)

    async def ack_many(self, messages: ConcurrentStableList[ReceivedMessage]) -> CommitResult:
        """按顺序确认一批消息（服务端无批量端点，逐条等价封装）。

        Args:
            messages: 待确认消息。

        Returns:
            CommitResult: 最后一条确认后的已提交位点（空列表返回 0）。

        Raises:
            MsgClientError: 任一条被拒绝。
        """
        committed = CommitResult()
        for message in messages:
            committed = await self.ack(message)
        return committed

    async def nack(self, message: ReceivedMessage, *, reason: str = "processing_failed") -> CommitResult:
        """拒绝一条消息（转死信 + 位点前移）。

        Args:
            message: 拒收的消息。
            reason: 原因（`schema_invalid` / `processing_failed`）。

        Returns:
            CommitResult: 已提交位点。

        Raises:
            ParamError: 原因非法 / 客户端已关闭。
            MsgClientError: 服务端拒绝。
        """
        if reason not in ("schema_invalid", "processing_failed"):
            raise ParamError(f"reason 只能是 schema_invalid 或 processing_failed（当前 {reason}）")
        return await self._settle(NACK_PATH, message, frame_type=int(FrameType.NACK), extra=("reason", reason))

    async def heartbeat(self) -> Assignment:
        """发一次心跳（顺带取回可能变化的分配）。

        Returns:
            Assignment: 最新分配。

        Raises:
            MsgClientError: 组不存在 / 成员失效。
        """
        outcome = await self._request(
            HEARTBEAT_PATH, frame_type=int(FrameType.MEMBER_HEARTBEAT), fields=self._member_fields()
        )
        assignment = self._assignment_of(outcome.data)
        self._assignment = assignment
        self.stats.incr("heartbeat_total")
        return assignment

    def heartbeat_delay_ms(self) -> int:
        """心跳间隔（取服务端给的间隔 × 0.6，下限 1 秒）。

        Returns:
            int: 毫秒。
        """
        interval = self._assignment.heartbeat_interval_ms if self._assignment is not None else 10_000
        return max(int(interval * _HEARTBEAT_INTERVAL_RATIO), _MIN_HEARTBEAT_INTERVAL_MS)

    async def close(self) -> None:
        """停止心跳、离开组、关闭传输层（幂等）。

        **离开失败只记计数**：进程退出路径不该因为「组已不存在」而抛错。
        """
        if self._closed:
            return
        self._closed = True
        task = self._heartbeat_task
        self._heartbeat_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        try:
            await self._leave()
        except MsgClientError as exc:
            self.stats.incr("leave_failed_total", code=str(exc.code))
        await self.transport.close()

    async def _settle(
        self,
        path: str,
        message: ReceivedMessage,
        *,
        frame_type: int,
        extra: tuple[str, str] | None,
    ) -> CommitResult:
        """确认 / 拒绝的公共实现（两者请求体只差 `reason`）。

        Args:
            path: 端点路径。
            message: 目标消息。
            frame_type: 帧类型（`ACK` / `NACK`）。
            extra: 额外的单个键值（`nack` 的 `reason`）。

        Returns:
            CommitResult: 已提交位点。

        Raises:
            MsgClientError: 服务端拒绝。
        """
        self._ensure_open()
        fields: ConcurrentStableDict[str, object] = self._member_fields()
        fields.set("partition", message.partition)
        fields.set("offset", message.offset)
        if extra is not None:
            fields.set(extra[0], extra[1])
        outcome = await self._request(path, frame_type=frame_type, fields=fields)
        return CommitResult(committed_offset=_as_int(outcome.data.get("committed_offset")))

    async def _heartbeat_loop(self) -> None:
        """按服务端间隔发心跳（失败只记计数，成员失效由 `poll` 的重连处置）。"""
        while not self._closed:
            await self.config.clock.sleep_ms(self.heartbeat_delay_ms())
            if self._closed:
                return
            try:
                await self.heartbeat()
            except MsgClientError as exc:
                self.stats.incr("heartbeat_failed_total", code=str(exc.code))

    async def _leave(self) -> None:
        """发离开请求（幂等；组不存在也返回成功）。

        Raises:
            MsgClientError: 服务端拒绝。
        """
        await self._request(LEAVE_PATH, frame_type=int(FrameType.LEAVE), fields=self._member_fields())

    def _member_fields(self) -> ConcurrentStableDict[str, object]:
        """成员三端点的公共字段（`join` / `heartbeat` / `leave` 只差这几项）。

        Returns:
            ConcurrentStableDict[str, object]: 字段（组 / 命名空间 / 主题 / 成员标识）。
        """
        return ConcurrentStableDict(
            {
                "group": self.group,
                "namespace": self.namespace,
                "topic": self.topic,
                "consumer_id": self.consumer_id,
            }
        )

    async def _request(
        self,
        path: str,
        *,
        frame_type: int,
        fields: ConcurrentStableDict[str, object],
    ) -> ApiOutcome:
        """发请求并按消费端码表分类（`code != 0` 即抛）。

        Args:
            path: 端点路径。
            frame_type: 帧类型（每个端点一个，不存在「无帧形态」的端点）。
            fields: 业务字段。

        Returns:
            ApiOutcome: 传输层解析结果（`code == 0`）。

        Raises:
            MsgClientError: 服务端拒绝（按码表分类）。
        """
        request = ApiRequest(
            frame_type=frame_type,
            path=path,
            fields=ConcurrentStableFrozenDict(fields),
        )
        outcome = await self.transport.post(self._endpoint(), request)
        if outcome.code == 0:
            return outcome
        rule = rule_for_consume(outcome.code)
        raise MsgClientError(
            code=outcome.code,
            category=rule.category,
            action=rule.action,
            message=outcome.message,
            data=outcome.data,
            outcome_unknown=rule.outcome_unknown,
            retry_after_ms=outcome.retry_after_ms,
        )

    def _endpoint(self) -> str:
        """轮询选地址（消费是读路径，任一实例都行；分摊负载）。

        Returns:
            str: 服务地址。
        """
        endpoints = self.config.endpoints
        endpoint = endpoints[self._endpoint_cursor % len(endpoints)]
        self._endpoint_cursor += 1
        return endpoint

    def _next_partition(self) -> int:
        """分配内轮转取下一个分区。

        Returns:
            int: 分区号。
        """
        assignment = cast("Assignment", self._assignment)
        partition = assignment.partitions[self._cursor % len(assignment.partitions)]
        self._cursor += 1
        return partition

    def _assignment_of(self, data: ConcurrentStableFrozenDict[str, object]) -> Assignment:
        """把响应 `data` 转成分配对象。

        Args:
            data: 响应 `data`。

        Returns:
            Assignment: 分配。
        """
        partitions: ConcurrentStableList[int] = ConcurrentStableList()
        for item in _items(data.get("partitions")):
            partitions.add(_as_int(item, -1))
        return Assignment(
            group=str(data.get("group") or self.group),
            topic=str(data.get("topic") or self.topic),
            consumer_id=str(data.get("consumer_id") or self.consumer_id),
            generation=_as_int(data.get("generation")),
            state=str(data.get("state") or ""),
            partitions=ConcurrentStableFrozenList(partitions),
            member_count=_as_int(data.get("member_count")),
            heartbeat_interval_ms=_as_int(data.get("heartbeat_interval_ms"), 10_000),
            session_timeout_ms=_as_int(data.get("session_timeout_ms"), 30_000),
        )

    def _poll_result(self, outcome: ApiOutcome, partition: int) -> PollResult:
        """把响应转成拉取结果（消息体优先取帧通道的切片，否则解 base64）。

        Args:
            outcome: 传输层解析结果（`payload_segments` 与 `data["messages"]` 按下标对应）。
            partition: 本次拉取的分区号。

        Returns:
            PollResult: 拉取结果。
        """
        data = outcome.data
        segments = outcome.payload_segments
        messages: ConcurrentStableList[ReceivedMessage] = ConcurrentStableList()
        for index, item in enumerate(_items(data.get("messages"))):
            if not isinstance(item, dict):
                continue
            payload = segments[index] if index < len(segments) else None
            messages.add(self._message_of(cast("object", item), partition, payload))
        return PollResult(
            messages=ConcurrentStableFrozenList(messages),
            partition=partition,
            paused=bool(data.get("paused")),
            inflight_messages=_as_int(data.get("inflight_messages")),
            inflight_bytes=_as_int(data.get("inflight_bytes")),
        )

    def _message_of(self, item: object, partition: int, payload: bytes | None) -> ReceivedMessage:
        """把一条 `MessageItem` 转成 `ReceivedMessage`。

        Args:
            item: 响应里的一条消息（内置 dict）。
            partition: 本次拉取的分区号。
            payload: 消息体原始字节（帧通道给值；None 表示按 JSON 的 base64 字段解码）。

        Returns:
            ReceivedMessage: 消息对象。
        """
        raw: dict[str, object] = cast("dict[str, object]", item)  # bare-collections:allow（响应体是内置 JSON 结构）
        encoded = raw.get("payload")
        headers = raw.get("headers")
        return ReceivedMessage(
            message_id=str(raw.get("message_id") or ""),
            topic=str(raw.get("topic") or self.topic),
            partition=_as_int(raw.get("partition"), partition),
            offset=_as_int(raw.get("offset")),
            payload=payload if payload is not None else (base64.b64decode(str(encoded)) if encoded else b""),
            key=None if raw.get("key") is None else str(raw.get("key")),
            headers=ConcurrentStableFrozenDict(
                _headers_of(headers),
            ),
            delivery_count=_as_int(raw.get("delivery_count"), 1),
            published_at=str(raw.get("published_at") or ""),
            content_type=str(raw.get("content_type") or ""),
            compression=str(raw.get("compression") or "none"),
            uncompressed_len=_as_optional_int(raw.get("uncompressed_len")),
            trace_id=None if raw.get("trace_id") is None else str(raw.get("trace_id")),
            span_id=None if raw.get("span_id") is None else str(raw.get("span_id")),
            trace_flags=None if raw.get("trace_flags") is None else str(raw.get("trace_flags")),
        )

    def _ensure_open(self) -> None:
        """关闭后拒绝再操作（编程错误，用 `ParamError` 而不是产品码）。

        Raises:
            ParamError: 已关闭。
        """
        if self._closed:
            raise ParamError("客户端已关闭：请新建实例")
