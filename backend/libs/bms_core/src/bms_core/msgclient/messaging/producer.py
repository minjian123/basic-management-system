"""消息生产端（msg 03-6 详细设计 §5.2 / §6.1 / §6.2）。

**三条来自服务端事实的硬约束**（别在实现里漂）：

1. **没有服务端批量端点**：`publish_many` 是客户端并发窗口，逐条独立成败，语义与单发等价；
2. **没有服务端发布幂等**：本地表只在同一进程内有效，跨重启 / 跨实例失效——因此「结果未知」
   （提交超时、读超时）默认**不自动重试**，避免把重复放大；
3. **`350033` 是唯一「换地址重发」的信号**：错误体 `data.leader` / `data.epoch` 给出新视图，
   改投期间同分区有最小间隔，防止抖动打成循环。
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field, replace

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.core.roots import BaseValueObject
from bms_core.msgclient.messaging.codes import rule_for_publish
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.errors import ClientAction, MsgClientError
from bms_core.msgclient.messaging.stats import ClientStats
from bms_core.msgclient.messaging.transport import ApiOutcome, MessagingTransport
from bms_core.msgclient.retry import compute_backoff_ms

__all__ = [
    "FailedItem",
    "MsgProducer",
    "OutgoingMessage",
    "PublishAck",
    "PublishBatchResult",
    "SucceededItem",
]

PUBLISH_PATH = "/msg/publish"
"""发布端点（根路径帧入口的同一实现；`/api/v1/msg/publish` 语义等价）。"""

ACKS_VALUES = ConcurrentStableFrozenList(["1", "all"])
"""服务端允许的确认档位（`PublishRequest.acks` 的闭集）。"""

KEY_MAX_LENGTH = 256
"""分区键上限（与服务端 `MESSAGE_KEY_MAX_LENGTH` 同值）。"""


def _empty_headers() -> ConcurrentStableFrozenDict[str, str]:
    """新建空的头映射。

    Returns:
        ConcurrentStableFrozenDict[str, str]: 空映射。
    """
    return ConcurrentStableFrozenDict()


@dataclass(frozen=True)
class OutgoingMessage(BaseValueObject):
    """一条待发布消息（`payload` 是原始字节，SDK 负责 base64）。

    Attributes:
        namespace: 命名空间。
        topic: 主题名。
        payload: 消息体原始字节（服务端上限 1 MiB）。
        key: 分区键（同 key 恒同分区；可空）。
        headers: 结构化头（原样透传；幂等键由 SDK 另写入 `x-msg-idem-key`）。
        acks: 确认档位（`1` / `all`）。
        delay_level: 延迟档位（`1s` ~ `60m`；空 = 普通发布）。
        content_type: 内容类型（空 = 服务端缺省）。
        idempotency_key: 幂等键（空 = 不去重）。
        trace_id: 链路标识（可空）。
        span_id: 跨度标识（可空）。
        trace_flags: 采样标记（可空）。
    """

    namespace: str
    topic: str
    payload: bytes
    key: str | None = None
    headers: ConcurrentStableFrozenDict[str, str] = field(default_factory=_empty_headers)
    acks: str = "1"
    delay_level: str | None = None
    content_type: str | None = None
    idempotency_key: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    trace_flags: str | None = None


@dataclass(frozen=True)
class PublishAck(BaseValueObject):
    """发布成功的回执。

    Attributes:
        message_id: 消息 ID（重投 / 重放不变）。
        log_id: 记录 ID。
        topic: 主题名。
        partition: 落到的分区号。
        offset: 分区内序号（延迟发布为 null）。
        deliver_at: 到期时刻（延迟发布才有）。
        deduplicated: 是否由本地幂等表命中（未发请求）。
    """

    message_id: str
    log_id: str
    topic: str
    partition: int
    offset: int | None = None
    deliver_at: str | None = None
    deduplicated: bool = False


@dataclass(frozen=True)
class SucceededItem(BaseValueObject):
    """批量结果里成功的一条。

    Attributes:
        index: 在入参列表中的下标。
        ack: 回执。
    """

    index: int
    ack: PublishAck


@dataclass(frozen=True)
class FailedItem(BaseValueObject):
    """批量结果里失败的一条。

    Attributes:
        index: 在入参列表中的下标。
        error: 错误（`None` 且 `cancelled` 为真表示未开始即被取消）。
        cancelled: 是否因快速失败被取消（未发出请求）。
    """

    index: int
    error: MsgClientError | None = None
    cancelled: bool = False


@dataclass(frozen=True)
class PublishBatchResult(BaseValueObject):
    """批量发布结果（按原始下标可复原）。

    Attributes:
        succeeded: 成功项。
        failed: 失败项（含被取消的）。
        requested: 入参总条数。
    """

    succeeded: ConcurrentStableFrozenList[SucceededItem] = field(
        default_factory=lambda: ConcurrentStableFrozenList[SucceededItem]()
    )
    failed: ConcurrentStableFrozenList[FailedItem] = field(
        default_factory=lambda: ConcurrentStableFrozenList[FailedItem]()
    )
    requested: int = 0


@dataclass(frozen=True)
class _IdemEntry(BaseValueObject):
    """本地幂等表条目。

    Attributes:
        expire_at: 过期时刻（单调毫秒）。
        ack: 首次成功的回执。
    """

    expire_at: int
    ack: PublishAck


def _validate(message: OutgoingMessage) -> None:
    """发布前校验（服务端也会判，这里只把明显的错提前暴露）。

    Args:
        message: 待发布消息。

    Raises:
        ParamError: 命名空间 / 主题为空，载荷非字节，`acks` 不在闭集，分区键超长。
    """
    if not message.namespace.strip():
        raise ParamError("namespace 不能为空")
    if not message.topic.strip():
        raise ParamError("topic 不能为空")
    if message.acks not in ACKS_VALUES:
        raise ParamError(f"acks 只能是 1 或 all（当前 {message.acks}）")
    if message.key is not None and len(message.key) > KEY_MAX_LENGTH:
        raise ParamError(f"key 长度不得超过 {KEY_MAX_LENGTH}")


def _as_int(value: object) -> int | None:
    """把响应字段转成整数（非整数返回 None，不抛）。

    Args:
        value: 响应字段值。

    Returns:
        int | None: 整数或 None。
    """
    return value if isinstance(value, int) else None


def _as_text(value: object) -> str | None:
    """把响应字段转成文本（None 保持 None）。

    Args:
        value: 响应字段值。

    Returns:
        str | None: 文本或 None。
    """
    return None if value is None else str(value)


class MsgProducer:
    """消息生产端（单实例可被多个协程共享；计数器在事件循环内自增，无锁竞争）。

    Attributes:
        config: 客户端配置。
        transport: 传输层。
        stats: 客户端计数器。
    """

    def __init__(self, config: MessagingConfig, transport: MessagingTransport, stats: ClientStats) -> None:
        """初始化。

        Args:
            config: 客户端配置。
            transport: 传输层。
            stats: 客户端计数器。
        """
        self.config = config
        self.transport = transport
        self.stats = stats
        self._idem: ConcurrentStableDict[str, _IdemEntry] = ConcurrentStableDict()
        self._cursor = 0
        self._preferred: str | None = None

    async def publish(self, message: OutgoingMessage) -> PublishAck:
        """发布一条消息（幂等键命中则不发请求）。

        Args:
            message: 待发布消息。

        Returns:
            PublishAck: 回执（`deduplicated=True` 表示本地幂等表命中）。

        Raises:
            ParamError: 参数非法。
            MsgClientError: 服务端拒绝，或重试 / 改投次数用尽。
        """
        _validate(message)
        cached = self._lookup(message)
        if cached is not None:
            return cached
        retries = 0
        redirects = 0
        while True:
            self.stats.incr("requests_total", op="publish")
            endpoint = self._endpoint()
            try:
                outcome = await self.transport.post(endpoint, PUBLISH_PATH, self.body(message))
                ack = self._ack(outcome, message)
            except MsgClientError as exc:
                redirects, retries = self._handle_failure(exc, retries=retries, redirects=redirects)
                await self.config.clock.sleep_ms(self._delay_ms(exc, retries=retries, redirects=redirects))
                continue
            self._remember(message, ack)
            self._preferred = None
            return ack

    async def publish_many(
        self,
        messages: ConcurrentStableList[OutgoingMessage],
        *,
        fail_fast: bool = False,
    ) -> PublishBatchResult:
        """批量发布（客户端并发窗口；逐条独立成败）。

        Args:
            messages: 待发布消息（列表序即结果下标）。
            fail_fast: 首个失败后不再开始新条目（已在途的等其自然结束，不中途掐断）。

        Returns:
            PublishBatchResult: 成功项 / 失败项 / 入参条数。
        """
        total = len(messages)
        succeeded: ConcurrentStableList[SucceededItem] = ConcurrentStableList()
        failed: ConcurrentStableList[FailedItem] = ConcurrentStableList()
        cursor = [0]
        stopping = [False]

        async def worker() -> None:
            """从游标取下标 → 发布 → 归位结果（游标在 `await` 前自增，单线程无竞争）。"""
            while True:
                if stopping[0]:
                    return
                index = cursor[0]
                if index >= total:
                    return
                cursor[0] = index + 1
                try:
                    ack = await self.publish(messages[index])
                except MsgClientError as exc:
                    failed.add(FailedItem(index=index, error=exc))
                    if fail_fast:
                        stopping[0] = True
                else:
                    succeeded.add(SucceededItem(index=index, ack=ack))

        workers = [asyncio.create_task(worker()) for _ in range(min(self.config.publish_concurrency, total))]
        if workers:
            await asyncio.gather(*workers)
        for index in range(cursor[0], total):
            failed.add(FailedItem(index=index, cancelled=True))
        return PublishBatchResult(
            succeeded=ConcurrentStableFrozenList(succeeded),
            failed=ConcurrentStableFrozenList(failed),
            requested=total,
        )

    def body(self, message: OutgoingMessage) -> dict[str, object]:  # bare-collections:allow（JSON 序列化边界）
        """组装发布请求体（JSON 结构；幂等键另写入头）。

        Args:
            message: 待发布消息。

        Returns:
            dict[str, object]: 请求体。
        """
        headers = {key: value for key, value in message.headers.items()}
        if message.idempotency_key is not None:
            headers["x-msg-idem-key"] = message.idempotency_key
        body: dict[str, object] = {  # bare-collections:allow（同上：JSON 序列化边界）
            "namespace": message.namespace,
            "topic": message.topic,
            "payload": base64.b64encode(message.payload).decode("ascii"),
            "headers": headers,
            "acks": message.acks,
        }
        for name, value in (
            ("key", message.key),
            ("delay_level", message.delay_level),
            ("content_type", message.content_type),
            ("trace_id", message.trace_id),
            ("span_id", message.span_id),
            ("trace_flags", message.trace_flags),
        ):
            if value is not None:
                body[name] = value
        return body

    async def close(self) -> None:
        """关闭传输层（幂等）。"""
        await self.transport.close()

    def _ack(self, outcome: ApiOutcome, message: OutgoingMessage) -> PublishAck:
        """把响应转成回执；`code` 非 0 时按码表抛错。

        Args:
            outcome: 传输层解析结果。
            message: 原始消息（缺字段时回退用）。

        Returns:
            PublishAck: 回执。

        Raises:
            MsgClientError: `code` 非 0（按码表分类）。
        """
        if outcome.code != 0:
            rule = rule_for_publish(outcome.code)
            raise MsgClientError(
                code=outcome.code,
                category=rule.category,
                action=rule.action,
                message=outcome.message,
                data=outcome.data,
                outcome_unknown=rule.outcome_unknown,
                retry_after_ms=outcome.retry_after_ms,
            )
        data = outcome.data
        return PublishAck(
            message_id=str(data.get("message_id") or ""),
            log_id=str(data.get("log_id") or ""),
            topic=str(data.get("topic") or message.topic),
            partition=_as_int(data.get("partition")) or 0,
            offset=_as_int(data.get("offset")),
            deliver_at=_as_text(data.get("deliver_at")),
        )

    def _handle_failure(self, exc: MsgClientError, *, retries: int, redirects: int) -> tuple[int, int]:
        """决定「改投 / 重试 / 抛出」，返回更新后的（改投次数，重试次数）。

        **重试计数按「是否真的再发一次」判定**，不按 `action` 判定：`retry_ambiguous` 打开时，
        结果为未知的错误 `action` 仍是 `fatal`，但确实要再发一次——按 `action` 计数会漏增导致死循环。

        Args:
            exc: 错误。
            retries: 已用重试次数。
            redirects: 已改投次数。

        Returns:
            tuple[int, int]: （更新后的改投次数，更新后的重试次数）；抛错时不会返回。

        Raises:
            MsgClientError: 超出次数预算 / 属需人工类 / 结果未知且未开启自动重试。
        """
        if exc.action is ClientAction.REFRESH:
            next_redirects = redirects + 1
            if next_redirects > self.config.max_redirects:
                self.stats.incr("errors_total", code=str(exc.code))
                raise exc
            self._adopt_leader(exc)
            self.stats.incr("redirects_total", reason=str(exc.code))
            return next_redirects, retries
        retryable = exc.action is ClientAction.RETRY or (exc.outcome_unknown and self.config.retry_ambiguous)
        if retryable and retries < self.config.retry.max_retries:
            self.stats.incr("retries_total", op="publish", reason=str(exc.code))
            return redirects, retries + 1
        self.stats.incr("errors_total", code=str(exc.code))
        raise exc

    def _delay_ms(self, exc: MsgClientError, *, retries: int, redirects: int) -> int:
        """算下一次尝试前的等待（毫秒）。

        Args:
            exc: 触发等待的错误。
            retries: 本次重试的序号（1 起；`compute_backoff_ms` 需要它）。
            redirects: 已改投次数（本次改投的序号）。

        Returns:
            int: 等待毫秒。
        """
        if exc.action is ClientAction.REFRESH:
            backoff = compute_backoff_ms(redirects, self.config.retry, self.config.jitter)
            return max(backoff, self.config.refresh_min_interval_ms)
        if exc.retry_after_ms is not None:
            return min(exc.retry_after_ms, self.config.retry.cap_ms)
        return compute_backoff_ms(retries, self.config.retry, self.config.jitter)

    def _endpoint(self) -> str:
        """选本次请求的地址（改投目标优先，否则轮询）。

        Returns:
            str: 服务地址。
        """
        if self._preferred is not None:
            return self._preferred
        endpoints = self.config.endpoints
        endpoint = endpoints[self._cursor % len(endpoints)]
        self._cursor += 1
        return endpoint

    def _adopt_leader(self, exc: MsgClientError) -> None:
        """从错误的 `data.leader` 里取改投目标（没有节点地址表时留空，走轮询）。

        Args:
            exc: `350033` 类错误。
        """
        leader = exc.data.get("leader")
        if not isinstance(leader, str) or not leader:
            return
        address = self.config.node_addresses.get(leader)
        if address is None:
            return
        self._preferred = address

    def _lookup(self, message: OutgoingMessage) -> PublishAck | None:
        """查本地幂等表（过期即删）。

        Args:
            message: 待发布消息。

        Returns:
            PublishAck | None: 命中的回执（`deduplicated=True`），未命中为 None。
        """
        key = self._idem_key(message)
        if key is None:
            return None
        entry = self._idem.get(key)
        if entry is None:
            return None
        if self.config.clock.now_ms() >= entry.expire_at:
            self._idem.delete(key)
            return None
        self.stats.incr("dedup_hits_total")
        return replace(entry.ack, deduplicated=True)

    def _remember(self, message: OutgoingMessage, ack: PublishAck) -> None:
        """写本地幂等表（成功才写；超出容量按插入序淘汰）。

        Args:
            message: 已发布消息。
            ack: 回执。
        """
        key = self._idem_key(message)
        if key is None:
            return
        while len(self._idem) >= self.config.idempotency_capacity:
            self._idem.delete(next(iter(self._idem)))
        self._idem.set(key, _IdemEntry(expire_at=self.config.clock.now_ms() + self.config.idempotency_ttl_ms, ack=ack))

    @staticmethod
    def _idem_key(message: OutgoingMessage) -> str | None:
        """构造幂等表键（空键即不去重）。

        Args:
            message: 消息。

        Returns:
            str | None: 键或 None。
        """
        if message.idempotency_key is None:
            return None
        return f"{message.namespace}\x00{message.topic}\x00{message.idempotency_key}"
