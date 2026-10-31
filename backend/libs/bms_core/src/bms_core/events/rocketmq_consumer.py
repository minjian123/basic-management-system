"""事件消费组真实实现 `RocketMqEventConsumerGroup`：拉取 → 键级串行分发 → 幂等 → 重试 / 死信。

形态（《详细设计 · 事件总线》§4.3）：

- **一个消费组一个 `SimpleConsumer`**：组名 `{group_prefix}.{域}`，由各服务自持声明装载而来。
- **主动拉取而非推送回调**：`receive(max, invisible)` 是同步长轮询，放线程池执行；控制权在应用，
  停机时先停拉取、等在途跑完，语义清晰且可测。
- **键级串行**：同 `aggregate_key`（空回落租户、再回落事件 ID）哈希到固定道，道内串行——
  保证审计链「同租户 `prev_hash` 衔接」；`ordered` 组道数固定 1。
- **幂等**：先 `seen()` 只读预判（命中即 ack 跳过），业务成功后再 `remember()` 标记；
  真正的「效果一次」由处理器内 `ProcessedEventStore`（与业务同事务）兜底。
- **重试 / 死信**：应用内退避重试有限次 → 超限写死信并 ack（不再依赖 broker 反复重投，
  避免重试次数被两处放大）；**仅死信落库失败时不 ack**，让 broker 重投——宁可重复不可丢。
- **毒消息**：解码失败 / 无处理器 / 订阅不支持该主版本 → 直接死信 + ack（重试只会堵住同道队列）。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import EventConsumeError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseDataContract
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.events.base import (
    DEFAULT_CONSUME_BATCH,
    BaseEventConsumerGroup,
    ConsumedTally,
    EventConsumer,
    EventEnvelope,
)
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.contracts import EventSubscription, event_version_compatible, resolve_event_contract
from bms_core.events.dead_letter import EventDeadLetterEntry, EventDeadLetterRecorder
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.lane import KeyedLaneExecutor
from bms_core.events.topic import ATTR_EVENT_ID, decode_event, topic_for
from bms_core.metrics.base import BaseMetrics

__all__ = ["RocketMqEventConsumerGroup"]

_LOGGER = get_logger("bms")

_GROUP_REGISTER_WAIT_SECONDS = 1.5
"""首次建连后等待消费组在 broker 侧注册完成（秒）。"""

_METRIC_CONSUME = "bms_event_consume_total"
_METRIC_DEAD = "bms_event_dead_letter_total"


@dataclass
class _GroupRuntime(BaseDataContract):
    """单组运行时（处理器表 + 执行器 + 消费客户端）。"""

    name: str
    ordered: bool
    concurrency: int | None
    handlers: ConcurrentStableDict[str, EventConsumer] = field(
        default_factory=lambda: ConcurrentStableDict[str, EventConsumer]()
    )
    lanes: KeyedLaneExecutor | None = None
    consumer: Any = None
    task: asyncio.Task[None] | None = None

    def lanes_or_create(self) -> KeyedLaneExecutor:
        """取（或创建）键级执行器。

        Returns:
            KeyedLaneExecutor: 执行器（有序组 1 道）。
        """
        if self.lanes is None:
            self.lanes = KeyedLaneExecutor(1 if self.ordered else (self.concurrency or 1))
        return self.lanes


class RocketMqEventConsumerGroup(BaseEventConsumerGroup):
    """RocketMQ 消费组运行时（多组并行，组内键级串行）。"""

    plugin_name = "rocketmq"

    def __init__(
        self,
        *,
        settings: Settings,
        engine_registry: EngineRegistry,
        session_factory: SessionFactory | None = None,
        dedup: EventConsumeDedup | None = None,
        metrics: BaseMetrics | None = None,
        consumer_factory: Any = None,
    ) -> None:
        """初始化（不建连；`start()` 时才为每组建客户端）。

        Args:
            settings: 应用配置（`[event_consumer]` / `[rocketmq]`）。
            engine_registry: 引擎注册表（死信落库）。
            session_factory: 会话工厂（死信落库）。
            dedup: 幂等短窗口（缺省按配置构造）。
            metrics: 指标器（可选）。
            consumer_factory: 消费客户端工厂 `(group, topics) -> consumer`（单测注入替身）。
        """
        self._settings = settings
        self._engine_registry = engine_registry
        self._session_factory = session_factory
        consumer_settings = settings.event_consumer
        self._dedup = dedup or EventConsumeDedup(ttl=consumer_settings.dedup_ttl_seconds)
        self._metrics = metrics
        self._consumer_factory = consumer_factory
        self._dead_letters = EventDeadLetterRecorder(engine_registry=engine_registry, session_factory=session_factory)
        self._groups: ConcurrentStableDict[str, _GroupRuntime] = ConcurrentStableDict()
        self._records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
        self._running = False

    @property
    def enabled(self) -> bool:
        """消费是否启用（`[event_consumer].enabled`）。"""
        return bool(self._settings.event_consumer.enabled)

    @property
    def dead_letter_recorder(self) -> EventDeadLetterRecorder:
        """死信写入器（诊断 / 测试注入故障用）。

        Returns:
            EventDeadLetterRecorder: 写入器。
        """
        return self._dead_letters

    @property
    def host(self) -> str:
        """宿主形态（`in_service` / `worker`）。"""
        return self._settings.event_consumer.host

    @property
    def groups(self) -> ConcurrentStableList[str]:
        """已装载的组名（诊断用）。"""
        return ConcurrentStableList(self._groups.keys())

    def load(self, records: ConcurrentStableList[EventConsumerRecord]) -> None:
        """装载声明（按组建处理器表，不启动）。

        Args:
            records: 合并后的组声明。
        """
        for record in records:
            runtime = self._groups.get(record.consumer)
            if runtime is None:
                runtime = _GroupRuntime(
                    name=record.consumer,
                    ordered=record.ordered,
                    concurrency=record.concurrency,
                )
                self._groups[record.consumer] = runtime
            if runtime.handlers.get(record.event_type) is None:
                runtime.handlers[record.event_type] = record.handler_factory()
            self._records.add(record)

    def subscriptions(self) -> ConcurrentStableList[EventSubscription]:
        """由声明派生订阅清单（供契约覆盖校验与启动日志）。"""
        return ConcurrentStableList(
            EventSubscription(
                consumer=record.consumer,
                event_type=record.event_type,
                description=record.description,
            )
            for record in self._records
        )

    async def setup(self) -> None:
        """装配期钩子：仅当「启用且宿主为服务进程」时启动后台消费。"""
        if self.enabled and self.host == "in_service":
            await self.start()

    async def start(self) -> None:
        """启动各组的后台消费循环（幂等）。"""
        if self._running or not self._groups:
            return
        self._running = True
        for runtime in self._groups.values():
            # 预建客户端：端点未配置 / SDK 缺失在启动期暴露（拒启），不拖到第一轮拉取
            self._consumer(runtime)
            runtime.task = asyncio.create_task(self._run_group(runtime))
        _LOGGER.info("event_consumer_started", groups=list(self._groups.keys()), host=self.host)

    async def stop(self) -> None:
        """停止后台消费并等待在途完成（幂等）。"""
        self._running = False
        for runtime in self._groups.values():
            task = runtime.task
            runtime.task = None
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            if runtime.lanes is not None:
                await runtime.lanes.aclose()
                runtime.lanes = None
            consumer = runtime.consumer
            runtime.consumer = None
            if consumer is not None:
                try:
                    await asyncio.to_thread(consumer.shutdown)
                except Exception as exc:  # 关闭失败不阻断其它组
                    _LOGGER.warning("event_consumer_shutdown_failed", group=runtime.name, error=repr(exc))

    async def aclose(self) -> None:
        """释放资源（幂等；随 `ResourceManager` 逆序回收）。"""
        await self.stop()

    async def consume_once(self, *, max_messages: int = DEFAULT_CONSUME_BATCH) -> ConsumedTally:
        """对各组执行一轮拉取消费（诊断 / 集成验证用，不依赖后台循环）。

        Args:
            max_messages: 单组单轮拉取上限。

        Returns:
            ConsumedTally: 汇总结果。
        """
        total = ConsumedTally()
        for runtime in self._groups.values():
            total = total.merge(await self._poll_once(runtime, max_messages=max_messages))
        return total

    async def _run_group(self, runtime: _GroupRuntime) -> None:
        """单组后台循环（取消即退出）。

        Args:
            runtime: 组运行时。
        """
        interval = self._settings.event_consumer.poll_interval_seconds
        while self._running:
            try:
                await self._poll_once(runtime, max_messages=self._settings.event_consumer.batch_size)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # 单轮异常不终止该组
                _LOGGER.warning("event_consumer_poll_error", group=runtime.name, error=repr(exc))
                await asyncio.sleep(interval)

    async def _poll_once(self, runtime: _GroupRuntime, *, max_messages: int) -> ConsumedTally:
        """拉取一批并处理（长轮询阻塞在线程池）。

        Args:
            runtime: 组运行时。
            max_messages: 本批上限。

        Returns:
            ConsumedTally: 本批汇总。
        """
        consumer = self._consumer(runtime)
        consumer_settings = self._settings.event_consumer
        messages = await asyncio.to_thread(consumer.receive, max_messages, consumer_settings.visibility_timeout_seconds)
        if not messages:
            return ConsumedTally()
        return await self._handle_batch(runtime, messages)

    async def _handle_batch(self, runtime: _GroupRuntime, messages: Any) -> ConsumedTally:
        """分发一批消息（键级串行），并按结果 ack。

        Args:
            runtime: 组运行时。
            messages: SDK 消息列表。

        Returns:
            ConsumedTally: 本批汇总。
        """
        runtime.lanes_or_create()
        outcomes = await asyncio.gather(*(self._process_one(runtime, message) for message in messages))
        succeeded = skipped = retried = dead = 0
        ackable: ConcurrentStableList[Any] = ConcurrentStableList()
        for message, outcome in zip(messages, outcomes, strict=False):
            kind, ack_now = outcome
            if kind == "succeeded":
                succeeded += 1
            elif kind == "skipped":
                skipped += 1
            elif kind == "retried":
                retried += 1
            else:
                dead += 1
            if ack_now:
                ackable.add(message)
        consumer = self._consumer(runtime)
        for message in ackable:
            try:
                await asyncio.to_thread(consumer.ack, message)
            except Exception as exc:  # ack 失败：本轮不重试，靠可见性超时重投
                _LOGGER.warning("event_consumer_ack_failed", group=runtime.name, error=repr(exc))
        tally = ConsumedTally(received=len(messages), succeeded=succeeded, skipped=skipped, retried=retried, dead=dead)
        await self._report(tally, group=runtime.name)
        return tally

    async def _process_one(self, runtime: _GroupRuntime, message: Any) -> tuple[str, bool]:
        """处理单条消息（同 key 串行）：

        Returns:
            tuple[str, bool]: （结果类别，是否可 ack）。
        """
        event_type_attr = _message_property(message, "event_type")
        try:
            event = decode_event(message.body or b"", _message_properties(message))
        except EventConsumeError as exc:
            return await self._to_dead_letter(runtime, message, event_type_attr or "unknown", str(exc))
        handler = runtime.handlers.get(event.event_type)
        if handler is None:
            return await self._to_dead_letter(
                runtime, message, event.event_type, f"无处理器（组未声明该事件）：{event.event_type}", event=event
            )
        contract = resolve_event_contract(event.event_type)
        if contract is not None and not event_version_compatible(contract, event.event_version):
            return await self._to_dead_letter(
                runtime,
                message,
                event.event_type,
                f"订阅不支持该契约版本：{event.event_version}",
                event=event,
            )
        # 幂等预判 + 处理 + 标记**整体进串行道**：同批次里同一 event_id 的两条消息若并发预判，
        # 都会在对方标记之前读到「未处理」→ 重复执行。同 key 串行后，后一条必然看到前一条的标记。
        lanes = runtime.lanes_or_create()
        return await lanes.submit(
            _partition_key(event),
            lambda: self._consume_once_deduped(runtime, event, handler),
        )

    async def _consume_once_deduped(
        self, runtime: _GroupRuntime, event: EventEnvelope, handler: EventConsumer
    ) -> tuple[str, bool]:
        """串行道内执行「预判 → 处理 → 标记」。（返回值同 `_process_one`）。

        Args:
            runtime: 组运行时。
            event: 事件信封。
            handler: 处理器。

        Returns:
            tuple[str, bool]: （结果类别，是否可 ack）。
        """
        if await self._dedup.seen(group=runtime.name, event_id=event.event_id or ""):
            return ("skipped", True)
        try:
            await handler.consume(event)
        except Exception as exc:
            return await self._retry_or_dead(runtime, None, event, exc)
        await self._dedup.remember(group=runtime.name, event_id=event.event_id or "")
        return ("succeeded", True)

    async def _retry_or_dead(
        self, runtime: _GroupRuntime, message: Any, event: EventEnvelope, error: Exception
    ) -> tuple[str, bool]:
        """应用内退避重试，耗尽后转死信。

        Args:
            runtime: 组运行时。
            message: 原始消息（死信用）。
            event: 事件信封。
            error: 首次失败原因。

        Returns:
            tuple[str, bool]: （结果类别，是否可 ack）。
        """
        settings = self._settings.event_consumer
        handler = runtime.handlers.get(event.event_type)
        if handler is None:  # pragma: no cover - 由调用方保证已取到
            return ("dead", True)
        last_error = error
        for attempt in range(1, settings.max_retries + 1):
            await asyncio.sleep(settings.retry_backoff_seconds * (2 ** (attempt - 1)))
            try:
                await handler.consume(event)
            except Exception as exc:  # 记录最近一次原因，继续退避
                last_error = exc
                continue
            await self._dedup.remember(group=runtime.name, event_id=event.event_id or "")
            return ("retried", True)
        return await self._to_dead_letter(
            runtime, message, event.event_type, f"重试 {settings.max_retries} 次仍失败：{last_error!r}", event=event
        )

    async def _to_dead_letter(
        self,
        runtime: _GroupRuntime,
        message: Any,
        event_type: str,
        error: str,
        *,
        event: EventEnvelope | None = None,
    ) -> tuple[str, bool]:
        """写死信（落库失败则不 ack，留给 broker 重投）。

        Args:
            runtime: 组运行时。
            message: 原始消息。
            event_type: 事件类型（解码失败时为属性值或 unknown）。
            error: 失败原因。
            event: 已解码事件（解码失败时为 None）。

        Returns:
            tuple[str, bool]: （`dead`，是否可 ack）。
        """
        entry = EventDeadLetterEntry(
            consumer=runtime.name,
            event_id=(event.event_id if event else None) or _message_property(message, ATTR_EVENT_ID) or "",
            event_type=event_type,
            error_msg=error,
            payload=ConcurrentStableFrozenDict(event.payload) if event else ConcurrentStableFrozenDict[str, object](),
            aggregate_key=event.aggregate_key if event else None,
            tenant_id=event.tenant_id if event else None,
            retry_count=self._settings.event_consumer.max_retries,
            occurred_at=event.occurred_at if event else None,
        )
        try:
            await self._dead_letters.record(entry)
        except Exception as exc:  # 死信落库失败：不 ack，等重投（宁可重复不可丢）
            _LOGGER.error("event_dead_letter_failed", group=runtime.name, error=repr(exc))
            return ("dead", False)
        return ("dead", True)

    def _consumer(self, runtime: _GroupRuntime) -> Any:
        """取（或创建）该组的消费客户端。

        Args:
            runtime: 组运行时。

        Returns:
            Any: SDK `SimpleConsumer` 或测试替身。
        """
        if runtime.consumer is not None:
            return runtime.consumer
        # 订阅按 **topic** 而非事件类型：多个事件类型可能落在同一 topic（域的同一对象），去重后订阅
        topics = ConcurrentStableList({topic_for(event_type) for event_type in runtime.handlers})
        if self._consumer_factory is not None:
            runtime.consumer = self._consumer_factory(runtime.name, topics)
        else:
            runtime.consumer = self._sdk_consumer(runtime.name, topics)
        return runtime.consumer

    def _sdk_consumer(self, group: str, topics: ConcurrentStableList[str]) -> Any:
        """建立消费客户端（端点校验可单测；SDK 构造见 `_build_sdk_consumer`）。

        Args:
            group: 消费组名。
            topics: 订阅 topic 清单。

        Returns:
            Any: SDK `SimpleConsumer`。

        Raises:
            EventConsumeError: 端点未配置。
        """
        rocketmq = self._settings.rocketmq
        if not rocketmq.endpoints:
            raise EventConsumeError(
                "RocketMQ 端点未配置（[rocketmq].endpoints / BMS_ROCKETMQ__ENDPOINTS）", data={"group": group}
            )
        return self._build_sdk_consumer(group, topics)

    def _build_sdk_consumer(self, group: str, topics: ConcurrentStableList[str]) -> Any:  # pragma: no cover
        """用官方 SDK 建连并订阅（**真机路径**：缺 broker / SDK 的单测不可达，由集成用例覆盖）。

        Args:
            group: 消费组名。
            topics: 订阅 topic 清单。

        Returns:
            Any: SDK `SimpleConsumer`。
        """
        rocketmq = self._settings.rocketmq
        try:
            from rocketmq import ClientConfiguration, Credentials, SimpleConsumer  # pyright: ignore[reportMissingTypeStubs]
        except ImportError as exc:
            raise EventConsumeError(
                "缺少 RocketMQ 客户端依赖（rocketmq-python-client）", data={"group": group}
            ) from exc
        has_credentials = bool(rocketmq.access_key and rocketmq.secret_key)
        credentials = Credentials(rocketmq.access_key, rocketmq.secret_key) if has_credentials else Credentials()
        # 长轮询时长必须**显著小于** gRPC 请求超时，否则 SDK 报 40018（deadline 不够 polling）
        poll_seconds = max(1, int(self._settings.event_consumer.poll_interval_seconds))
        request_timeout = max(int(rocketmq.request_timeout_seconds), poll_seconds + 5)
        config = (
            ClientConfiguration(rocketmq.endpoints, credentials, rocketmq.namespace, request_timeout=request_timeout)
            if rocketmq.namespace
            else ClientConfiguration(rocketmq.endpoints, credentials, request_timeout=request_timeout)
        )
        consumer = SimpleConsumer(config, group, await_duration=poll_seconds)
        consumer.startup()
        for topic in topics:
            cast("Any", consumer).subscribe(topic)
        # 消费组靠 heartbeat 在 broker 侧注册；注册完成前 proxy 的 receive 会抛 50001（NPE）。
        time.sleep(_GROUP_REGISTER_WAIT_SECONDS)
        _LOGGER.info("rocketmq_consumer_started", group=group, topics=list(topics), endpoints=rocketmq.endpoints)
        return consumer

    async def _report(self, tally: ConsumedTally, *, group: str) -> None:
        """上报消费计数（metrics 缺省时空操作）。

        Args:
            tally: 本批汇总。
            group: 组名。
        """
        if self._metrics is None:
            return
        for status, value in (
            ("succeeded", tally.succeeded),
            ("skipped", tally.skipped),
            ("retried", tally.retried),
            ("dead", tally.dead),
        ):
            if value:
                await self._metrics.counter(
                    _METRIC_CONSUME, value=float(value), labels={"group": group, "result": status}
                )
        if tally.dead:
            await self._metrics.counter(_METRIC_DEAD, value=float(tally.dead), labels={"consumer": group})


def _partition_key(event: EventEnvelope) -> str:
    """分区键：聚合键 → 租户 → 事件 ID（保证同聚合 / 同租户串行）。

    Args:
        event: 事件信封。

    Returns:
        str: 分区键。
    """
    return event.aggregate_key or event.tenant_id or event.event_id or ""


def _message_properties(message: Any) -> ConcurrentStableDict[str, str]:
    """取消息属性（SDK 为普通 dict，统一转并发字典）。

    Args:
        message: SDK 消息。

    Returns:
        ConcurrentStableDict[str, str]: 属性表。
    """
    raw: Any = getattr(message, "properties", None) or {}
    return ConcurrentStableDict({str(key): str(value) for key, value in cast("dict[Any, Any]", raw).items()})


def _message_property(message: Any, name: str) -> str | None:
    """取单个消息属性。

    Args:
        message: SDK 消息。
        name: 属性名。

    Returns:
        str | None: 属性值。
    """
    raw: Any = getattr(message, "properties", None) or {}
    value = cast("dict[Any, Any]", raw).get(name)
    return None if value is None else str(value)
