"""消费组运行时护栏：拉取 → 键级串行 → 幂等 → 重试 / 死信 → ack 语义。

依据《详细设计 · 事件总线》§4.3 / §4.5 / §4.6，锁住四条不能退让的语义：

1. 成功才 ack；重试耗尽→死信→ack（不让 broker 重复放大重试）；
2. 死信**落库失败不 ack**（宁可重复不可丢）；
3. 毒消息（解码失败 / 无处理器 / 版本不支持）直接死信，不进重试；
4. 同 key 严格串行，窗口内重复消息被幂等短窗口跳过。
"""

from datetime import UTC, datetime
from typing import Any, Literal, cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.events.rocketmq_consumer import RocketMqEventConsumerGroup
from bms_core.events.topic import encode_event, event_attributes
from bms_core.models.outbox import SysEventDeadLetter


class _Message:
    """消息替身（与 SDK `Message` 同形的最小字段集）。"""

    def __init__(
        self, event: EventEnvelope | None = None, *, body: bytes | None = None, properties: Any = None
    ) -> None:
        """初始化。

        Args:
            event: 事件信封（据此生成 body / properties）。
            body: 直接指定消息体（构造毒消息）。
            properties: 直接指定属性。
        """
        self.body = body if body is not None else encode_event(event)  # type: ignore[arg-type]
        self.properties = (
            dict(event_attributes(event)) if properties is None and event is not None else (properties or {})
        )
        self.acked = False


class _Consumer:
    """消费客户端替身：按批次返回预设消息并记录 ack。"""

    def __init__(self, batches: ConcurrentStableList[ConcurrentStableList[_Message]] | None = None) -> None:
        """初始化。

        Args:
            batches: 预设批次（每次 receive 取一批，取完返回空）。
        """
        self.batches = batches or ConcurrentStableList()
        self.acked: ConcurrentStableList[_Message] = ConcurrentStableList()
        self.shutdown_calls = 0

    def receive(self, max_message_num: int, invisible_duration: int) -> ConcurrentStableList[_Message]:
        """取下一批消息。

        Args:
            max_message_num: 上限（替身忽略）。
            invisible_duration: 可见性超时（替身忽略）。

        Returns:
            ConcurrentStableList[_Message]: 消息批次。
        """
        if not self.batches:
            return ConcurrentStableList()
        batch = self.batches[0]
        self.batches.remove(batch)
        return ConcurrentStableList(batch)

    def ack(self, message: _Message) -> None:
        """确认消息。

        Args:
            message: 消息。
        """
        message.acked = True
        self.acked.add(message)

    def shutdown(self) -> None:
        """关闭。"""
        self.shutdown_calls += 1


class _Handler(EventConsumer):
    """可编排失败的处理器。"""

    def __init__(self, event_type: str = "sys.user.created", *, fail_times: int = 0) -> None:
        """初始化。

        Args:
            event_type: 订阅的事件类型。
            fail_times: 前 N 次调用抛错。
        """
        self._event_type = event_type
        self.fail_times = fail_times
        self.calls = 0
        self.seen: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return self._event_type

    async def consume(self, event: EventEnvelope) -> None:
        """消费事件。

        Args:
            event: 事件信封。

        Raises:
            RuntimeError: 编排的失败。
        """
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(f"boom {self.calls}")
        self.seen.add(event.event_id or "")


@pytest.fixture(autouse=True)
def _platform_contracts() -> None:
    """登记平台默认事件契约（幂等）：版本兼容校验与真实启动路径同源。"""
    register_platform_event_contracts()


def _settings(*, enabled: bool = True, max_retries: int = 1, host: str = "in_service") -> Settings:
    """构造消费配置。

    Args:
        enabled: 消费开关。
        max_retries: 应用内重试次数。
        host: 宿主形态。

    Returns:
        Settings: 配置。
    """
    settings = Settings()
    settings.event_consumer.enabled = enabled
    settings.event_consumer.max_retries = max_retries
    settings.event_consumer.retry_backoff_seconds = 0.0
    settings.event_consumer.host = cast("Literal['in_service', 'worker']", host)
    return settings


def _event(
    event_id: str = "evt-1", *, tenant_id: str = "1234567890", aggregate_key: str = "1234567890"
) -> EventEnvelope:
    """构造事件。

    Args:
        event_id: 事件 ID。
        tenant_id: 租户。
        aggregate_key: 聚合键。

    Returns:
        EventEnvelope: 信封。
    """
    return EventEnvelope(
        event_type="sys.user.created",
        payload=ConcurrentStableDict({"user_id": "u-1"}),
        tenant_id=tenant_id,
        aggregate_key=aggregate_key,
        event_id=event_id,
        occurred_at=datetime(2026, 10, 31, tzinfo=UTC).replace(tzinfo=None),
    )


def _group(
    registry: EngineRegistry,
    consumer: _Consumer,
    handler: EventConsumer,
    *,
    settings: Settings | None = None,
) -> RocketMqEventConsumerGroup:
    """构造消费组（注入替身客户端与幂等短窗口）。

    Args:
        registry: 引擎注册表（死信落库）。
        consumer: 消费客户端替身。
        handler: 处理器。
        settings: 配置。

    Returns:
        RocketMqEventConsumerGroup: 运行时。
    """
    dedup = EventConsumeDedup(client=cast("Redis", FakeRedis()))
    group = RocketMqEventConsumerGroup(
        settings=settings or _settings(),
        engine_registry=registry,
        dedup=dedup,
        consumer_factory=lambda name, topics: consumer,
    )
    group.load(
        ConcurrentStableList(
            [
                EventConsumerRecord(
                    consumer="bms.audit.chain",
                    event_type=handler.event_type,
                    handler_factory=lambda: handler,
                    ordered=True,
                )
            ]
        )
    )
    return group


async def _dead_letters(registry: EngineRegistry) -> ConcurrentStableList[SysEventDeadLetter]:
    """读死信行。

    Args:
        registry: 引擎注册表。

    Returns:
        ConcurrentStableList[SysEventDeadLetter]: 死信行。
    """
    async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
        return ConcurrentStableList((await session.execute(select(SysEventDeadLetter))).scalars())


async def test_consume_once_success_acks_and_marks(dead_letter_registry: EngineRegistry) -> None:
    """成功消费：ack + 幂等标记；同事件再次投递被跳过。"""
    handler = _Handler()
    message = _Message(_event())
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([message])]))
    group = _group(dead_letter_registry, consumer, handler)

    first = await group.consume_once()
    assert (first.received, first.succeeded, first.dead) == (1, 1, 0)
    assert message.acked is True
    assert list(handler.seen) == ["evt-1"]

    # 同事件重投（模拟至少一次）：被短窗口拦下，不再进处理器
    repeat = _Message(_event())
    consumer.batches.add(ConcurrentStableList([repeat]))
    second = await group.consume_once()
    assert (second.skipped, second.succeeded) == (1, 0)
    assert repeat.acked is True
    assert handler.calls == 1
    await group.aclose()


async def test_poison_message_goes_dead_without_retry(dead_letter_registry: EngineRegistry) -> None:
    """毒消息（解码失败）直接死信并 ack，不进重试。"""
    handler = _Handler()
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([_Message(body=b"{not-json")])]))
    group = _group(dead_letter_registry, consumer, handler)

    tally = await group.consume_once()
    assert tally.dead == 1
    assert handler.calls == 0
    rows = await _dead_letters(dead_letter_registry)
    assert len(rows) == 1
    assert rows[0].consumer == "bms.audit.chain"
    assert "不是合法 JSON" in rows[0].error_msg
    await group.aclose()


async def test_no_handler_goes_dead(dead_letter_registry: EngineRegistry) -> None:
    """未声明该事件的处理器 → 死信（组不该收到不属于自己的事件）。"""
    handler = _Handler(event_type="sys.other.event")
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([_Message(_event())])]))
    group = _group(dead_letter_registry, consumer, handler)

    tally = await group.consume_once()
    assert tally.dead == 1
    rows = await _dead_letters(dead_letter_registry)
    assert "无处理器" in rows[0].error_msg
    await group.aclose()


async def test_retry_succeeds_within_limit(dead_letter_registry: EngineRegistry) -> None:
    """首次失败、重试成功 → 记为 retried 且 ack（不产生死信）。"""
    handler = _Handler(fail_times=1)
    message = _Message(_event())
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([message])]))
    group = _group(dead_letter_registry, consumer, handler, settings=_settings(max_retries=2))

    tally = await group.consume_once()
    assert (tally.retried, tally.dead) == (1, 0)
    assert message.acked is True
    assert await _dead_letters(dead_letter_registry) == []
    await group.aclose()


async def test_retry_exhausted_goes_dead_and_acks(dead_letter_registry: EngineRegistry) -> None:
    """重试耗尽 → 死信 + ack（不再让 broker 重投放大重试次数）。"""
    handler = _Handler(fail_times=10)
    message = _Message(_event())
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([message])]))
    group = _group(dead_letter_registry, consumer, handler, settings=_settings(max_retries=1))

    tally = await group.consume_once()
    assert tally.dead == 1
    assert message.acked is True
    rows = await _dead_letters(dead_letter_registry)
    assert len(rows) == 1
    assert "仍失败" in rows[0].error_msg
    assert rows[0].retry_count == 1
    await group.aclose()


async def test_dead_letter_failure_keeps_message_unacked(
    dead_letter_registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """死信落库失败 → 不 ack（留给 broker 重投；宁可重复不可丢）。"""
    handler = _Handler()
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([_Message(body=b"{bad")])]))
    group = _group(dead_letter_registry, consumer, handler)

    async def _boom(entry: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(group._dead_letters, "record", _boom)
    tally = await group.consume_once()
    assert tally.dead == 1
    assert len(consumer.acked) == 0
    await group.aclose()


async def test_same_key_processed_in_order(dead_letter_registry: EngineRegistry) -> None:
    """同聚合键两条消息按批次顺序串行处理。"""
    handler = _Handler()
    first, second = _Message(_event("evt-1")), _Message(_event("evt-2"))
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([first, second])]))
    group = _group(dead_letter_registry, consumer, handler)

    tally = await group.consume_once()
    assert tally.succeeded == 2
    assert list(handler.seen) == ["evt-1", "evt-2"]
    await group.aclose()


async def test_subscriptions_reflect_declarations(dead_letter_registry: EngineRegistry) -> None:
    """订阅清单由声明派生（供契约覆盖校验）。"""
    group = _group(dead_letter_registry, _Consumer(), _Handler())
    subscriptions = group.subscriptions()
    assert [(item.consumer, item.event_type) for item in subscriptions] == [("bms.audit.chain", "sys.user.created")]
    await group.aclose()


async def test_disabled_group_does_not_start(dead_letter_registry: EngineRegistry) -> None:
    """未启用时不启动后台循环（部署未就绪也不报错）。"""
    group = _group(dead_letter_registry, _Consumer(), _Handler(), settings=_settings(enabled=False))
    await group.setup()
    assert group.enabled is False
    await group.aclose()


async def test_stop_is_idempotent(dead_letter_registry: EngineRegistry) -> None:
    """停止可重复调用，并关闭消费客户端。"""
    consumer = _Consumer()
    group = _group(dead_letter_registry, consumer, _Handler())
    await group.start()
    await group.stop()
    await group.stop()
    assert consumer.shutdown_calls == 1
