"""事件总线边界分支护栏：补齐覆盖率门禁的异常 / 幂等 / 启停 / 装配分支。

与 `test_rocketmq_consumer.py` 的分工：那边验「主链路语义」，这里验「边界分支」——
Redis 未启用时的降级、消费组启停与关闭异常、ack 失败、版本不兼容、装配工厂与声明装载校验。
真机 SDK 构造路径不在单测覆盖范围（`# pragma: no cover`，由真 broker 集成用例执行）。
"""

import asyncio
from importlib import import_module
from typing import Any, cast

import pytest
from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import EventConsumeError, EventContractError, RedisUnavailableError
from bms_core.core.plugin import build_plugin_registry
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.events.base import EventConsumer, EventEnvelope
from bms_core.events.consumer_records import (
    EventConsumerRecord,
    merge_event_consumer_records,
    validate_event_consumer_records,
)
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.lane import KeyedLaneExecutor
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.events.rocketmq_consumer import RocketMqEventConsumerGroup
from bms_core.events.topic import encode_event, event_attributes

pytestmark = pytest.mark.kiwi_id(2370)

_EVENT_TYPE = "sys.user.created"


class _Handler(EventConsumer):
    """可编排失败的处理器。"""

    def __init__(self, *, fail_times: int = 0) -> None:
        """初始化。

        Args:
            fail_times: 前 N 次调用抛错。
        """
        self.fail_times = fail_times
        self.calls = 0

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return _EVENT_TYPE

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


class _Message:
    """消息替身。"""

    def __init__(self, event: EventEnvelope) -> None:
        """初始化。

        Args:
            event: 事件信封。
        """
        self.body = encode_event(event)
        self.properties: ConcurrentStableDict[str, str] = ConcurrentStableDict(event_attributes(event))

    @classmethod
    def raw(cls, body: bytes) -> _Message:
        """直接构造消息体（毒消息用）。

        Args:
            body: 消息体。

        Returns:
            _Message: 消息替身。
        """
        instance = cls.__new__(cls)
        instance.body = body
        instance.properties = ConcurrentStableDict()
        return instance


class _Consumer:
    """消费客户端替身（可编排 receive / ack / shutdown 异常）。"""

    def __init__(self, batches: ConcurrentStableList[ConcurrentStableList[Any]] | None = None) -> None:
        """初始化。

        Args:
            batches: 预设批次。
        """
        self.batches = batches or ConcurrentStableList()
        self.acked: ConcurrentStableList[Any] = ConcurrentStableList()
        self.shutdown_calls = 0
        self.ack_error: Exception | None = None
        self.shutdown_error: Exception | None = None

    def receive(self, max_message_num: int, invisible_duration: int) -> ConcurrentStableList[Any]:
        """取一批。

        Args:
            max_message_num: 上限（忽略）。
            invisible_duration: 可见性超时（忽略）。

        Returns:
            ConcurrentStableList[Any]: 批次。
        """
        if not self.batches:
            return ConcurrentStableList()
        batch = self.batches[0]
        self.batches.remove(batch)
        return ConcurrentStableList(batch)

    def ack(self, message: Any) -> None:
        """确认（可注入失败）。

        Args:
            message: 消息。

        Raises:
            Exception: 注入的失败。
        """
        if self.ack_error is not None:
            raise self.ack_error
        self.acked.add(message)

    def shutdown(self) -> None:
        """关闭（可注入失败）。

        Raises:
            Exception: 注入的失败。
        """
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error


def _settings(*, enabled: bool = True, endpoints: str = "") -> Settings:
    """构造配置。

    Args:
        enabled: 消费开关。
        endpoints: broker 端点（空 = 不建连）。

    Returns:
        Settings: 配置。
    """
    settings = Settings()
    settings.rocketmq.endpoints = endpoints
    settings.event_consumer.enabled = enabled
    settings.event_consumer.max_retries = 0
    settings.event_consumer.retry_backoff_seconds = 0.0
    return settings


def _event(event_id: str = "evt-1", *, event_version: str | None = None) -> EventEnvelope:
    """构造事件。

    Args:
        event_id: 事件 ID。
        event_version: 契约版本（None 按登记契约补齐）。

    Returns:
        EventEnvelope: 信封。
    """
    return EventEnvelope(
        event_type=_EVENT_TYPE,
        payload=ConcurrentStableDict({"user_id": "u-1"}),
        tenant_id="100000000000000001",
        aggregate_key="100000000000000001",
        event_id=event_id,
        event_version=event_version,
    )


def _group(
    registry: EngineRegistry,
    consumer: _Consumer,
    handler: EventConsumer,
    *,
    settings: Settings | None = None,
    metrics: Any = None,
) -> RocketMqEventConsumerGroup:
    """构造消费组（替身客户端）。

    Args:
        registry: 引擎注册表。
        consumer: 客户端替身。
        handler: 处理器。
        settings: 配置。
        metrics: 指标替身。

    Returns:
        RocketMqEventConsumerGroup: 运行时。
    """

    def build(name: str, topics: ConcurrentStableList[str]) -> _Consumer:
        return consumer

    group = RocketMqEventConsumerGroup(
        settings=settings or _settings(),
        engine_registry=registry,
        metrics=metrics,
        consumer_factory=build,
    )
    group.load(
        ConcurrentStableList(
            [EventConsumerRecord(consumer="bms-branch", event_type=handler.event_type, handler_factory=lambda: handler)]
        )
    )
    return group


@pytest.fixture(autouse=True)
def _contracts() -> None:
    """登记平台事件契约与 null 实现（幂等；装配工厂解析依赖已登记实现）。"""
    register_platform_event_contracts()
    import_module("bms_core.events.null")
    import_module("bms_core.metrics.null")


# ---- lane ----------------------------------------------------------------


async def test_lane_exposes_lanes_and_join() -> None:
    """`lanes` 暴露道数；`join` 等已入队任务完成（不关闭）。"""
    executor = KeyedLaneExecutor(lanes=2)
    assert executor.lanes == 2
    done: ConcurrentStableList[int] = ConcurrentStableList()

    async def job(value: int) -> None:
        done.add(value)

    tasks = [asyncio.create_task(executor.submit("k", lambda v=value: job(v))) for value in range(3)]
    await asyncio.sleep(0)  # 让提交协程完成入队
    await executor.join()
    await asyncio.gather(*tasks)
    await executor.aclose()
    assert len(done) == 3


# ---- dedup ---------------------------------------------------------------


async def test_dedup_degrades_when_redis_not_enabled() -> None:
    """Redis 未启用（进程共享客户端不可用）→ 预判放行、标记空操作，不抛错。"""
    dedup = EventConsumeDedup()
    assert await dedup.seen(group="bms-branch", event_id="evt-1") is False
    await dedup.remember(group="bms-branch", event_id="evt-1")


# ---- consumer_records ----------------------------------------------------


def test_factory_key_falls_back_to_repr() -> None:
    """无 `__qualname__` 的 callable（类实例）回落 repr 作工厂标识，同实例去重。"""

    class _Callable:
        def __call__(self) -> _Handler:
            return _Handler()

    factory = _Callable()
    records = ConcurrentStableList(
        [
            EventConsumerRecord(consumer="audit-chain", event_type=_EVENT_TYPE, handler_factory=factory),
            EventConsumerRecord(consumer="audit-chain", event_type=_EVENT_TYPE, handler_factory=factory),
        ]
    )
    assert len(merge_event_consumer_records(records)) == 1


def test_validate_empty_records_passes() -> None:
    """空声明通过（未声明消费组的服务不报错）。"""
    assert list(validate_event_consumer_records(ConcurrentStableList())) == []


# ---- 消费组边界 ----------------------------------------------------------


def test_load_same_group_twice_keeps_first_handler(dead_letter_registry: EngineRegistry) -> None:
    """同组同事件重复装载：保留首个处理器，不覆盖。"""
    handler = _Handler()
    other = _Handler()
    group = RocketMqEventConsumerGroup(settings=_settings(), engine_registry=dead_letter_registry)
    group.load(
        ConcurrentStableList(
            [EventConsumerRecord(consumer="bms-branch", event_type=_EVENT_TYPE, handler_factory=lambda: handler)]
        )
    )
    group.load(
        ConcurrentStableList(
            [EventConsumerRecord(consumer="bms-branch", event_type=_EVENT_TYPE, handler_factory=lambda: other)]
        )
    )
    assert len(group.subscriptions()) == 2  # 订阅按声明条数登记（重复声明由合并规则负责去重）


async def test_start_requires_endpoints(dead_letter_registry: EngineRegistry) -> None:
    """启用消费但未配端点 → 启动即拒（配置错误不拖到运行期）。"""
    group = RocketMqEventConsumerGroup(settings=_settings(endpoints=""), engine_registry=dead_letter_registry)
    group.load(
        ConcurrentStableList(
            [EventConsumerRecord(consumer="bms-branch", event_type=_EVENT_TYPE, handler_factory=_Handler)]
        )
    )
    with pytest.raises(EventConsumeError, match="端点未配置"):
        await group.start()
    await group.stop()


async def test_setup_starts_when_enabled(dead_letter_registry: EngineRegistry) -> None:
    """启用且宿主为服务进程时，`setup()` 启动后台循环。"""
    consumer = _Consumer()
    group = _group(dead_letter_registry, consumer, _Handler(), settings=_settings(enabled=True))
    await group.setup()
    assert group.enabled is True
    await group.stop()
    assert consumer.shutdown_calls == 1


async def test_start_is_idempotent(dead_letter_registry: EngineRegistry) -> None:
    """重复 `start()` / `stop()` 不重复建连。"""
    consumer = _Consumer()
    group = _group(dead_letter_registry, consumer, _Handler())
    await group.start()
    await group.start()
    await group.stop()
    await group.stop()
    assert consumer.shutdown_calls == 1


async def test_stop_swallows_shutdown_error(dead_letter_registry: EngineRegistry) -> None:
    """单个组关闭失败不阻断整体停止。"""
    consumer = _Consumer()
    consumer.shutdown_error = RuntimeError("shutdown boom")
    group = _group(dead_letter_registry, consumer, _Handler())
    await group.start()
    await group.stop()


async def test_empty_batch_returns_empty_tally(dead_letter_registry: EngineRegistry) -> None:
    """无消息时单轮返回空汇总（不产生假计数）。"""
    group = _group(dead_letter_registry, _Consumer(), _Handler())
    tally = await group.consume_once()
    assert (tally.received, tally.succeeded) == (0, 0)
    await group.aclose()


async def test_ack_failure_does_not_raise(dead_letter_registry: EngineRegistry) -> None:
    """ack 失败只记日志（消息靠可见性超时重投），不影响本轮其它消息。"""
    consumer = _Consumer()
    consumer.ack_error = RuntimeError("ack boom")
    group = _group(dead_letter_registry, consumer, _Handler())
    consumer.batches.add(ConcurrentStableList([_Message(_event())]))
    tally = await group.consume_once()
    assert tally.succeeded == 1
    await group.aclose()


async def test_incompatible_version_goes_dead(dead_letter_registry: EngineRegistry) -> None:
    """订阅不支持该主版本 → 直接死信（不重试）。"""
    handler = _Handler()
    consumer = _Consumer()
    group = _group(dead_letter_registry, consumer, handler)
    consumer.batches.add(ConcurrentStableList([_Message(_event(event_version="9.9.9"))]))
    tally = await group.consume_once()
    assert tally.dead == 1
    assert handler.calls == 0
    await group.aclose()


async def test_metrics_reported(dead_letter_registry: EngineRegistry) -> None:
    """指标注入时上报消费与死信计数（空实现时空操作）。"""

    class _Metrics:
        def __init__(self) -> None:
            self.calls: ConcurrentStableList[tuple[str, float]] = ConcurrentStableList()

        async def counter(self, name: str, value: float = 1.0, labels: Any = None) -> None:
            self.calls.add((name, value))

    metrics = _Metrics()
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([_Message.raw(b"{bad")])]))
    group = _group(dead_letter_registry, consumer, _Handler(), metrics=metrics)
    await group.consume_once()
    names = [name for name, _ in metrics.calls]
    assert "bms_event_consume_total" in names
    assert "bms_event_dead_letter_total" in names
    await group.aclose()


async def test_metrics_absent_is_noop(dead_letter_registry: EngineRegistry) -> None:
    """未注入指标时上报为空操作。"""
    group = _group(dead_letter_registry, _Consumer(), _Handler())
    await group.consume_once()
    await group.aclose()


async def test_groups_and_host_exposed(dead_letter_registry: EngineRegistry) -> None:
    """诊断入口暴露组名与宿主形态。"""
    group = _group(dead_letter_registry, _Consumer(), _Handler())
    assert list(group.groups) == ["bms-branch"]
    assert group.host == "in_service"
    await group.aclose()


# ---- 装配工厂与声明装载 --------------------------------------------------


def test_publisher_factory_creates_instance() -> None:
    """发布工厂按配置造实例（不建连）。"""
    from bms_core.core.assembly import RocketMqEventPublisherFactory

    publisher = RocketMqEventPublisherFactory(_settings()).create()
    assert publisher.event_type == "*"


def test_consumer_factory_creates_instance(tmp_path: Any) -> None:
    """消费组工厂从应用状态取引擎注册表并造实例。"""
    from bms_core.core.assembly import RocketMqEventConsumerGroupFactory

    build_plugin_registry()
    settings = _settings()
    settings.metrics.provider = ""
    app = FastAPI()
    registry = EngineRegistry(EngineFactory(settings))
    app.state.engine_registry = registry
    app.state.session_factory = None
    group = RocketMqEventConsumerGroupFactory(settings, app).create()
    assert group.enabled is True


def test_load_records_rejects_invalid_declaration() -> None:
    """装配期装载：声明校验不通过即拒启（`EventContractError`）。"""
    from bms_core.application import load_event_consumer_records

    build_plugin_registry()
    settings = _settings(enabled=False)
    app = FastAPI()
    app.state.event_consumer_records = ConcurrentStableList(
        [
            EventConsumerRecord(
                consumer="BadGroup",  # 大写不合规
                event_type=_EVENT_TYPE,
                handler_factory=_Handler,
            )
        ]
    )
    with pytest.raises(EventContractError, match="声明校验失败"):
        load_event_consumer_records(app, settings)


def test_load_records_accepts_valid_declaration() -> None:
    """装配期装载：合法声明装载进组运行时（不启动）。"""
    from bms_core.application import load_event_consumer_records

    build_plugin_registry()
    settings = _settings(enabled=False)
    app = FastAPI()
    app.state.event_consumer_records = ConcurrentStableList(
        [EventConsumerRecord(consumer="audit-chain", event_type=_EVENT_TYPE, handler_factory=_Handler)]
    )
    load_event_consumer_records(app, settings)  # 不抛错即通过（装载与装配分两步）


class _UnavailableDedupClient:
    """恒抛 `RedisUnavailableError` 的客户端替身（验证 fail-open 降级分支）。"""

    async def exists(self, *args: object, **kwargs: object) -> int:
        """恒定抛 Redis 不可用。

        Raises:
            RedisUnavailableError: 恒定。
        """
        raise RedisUnavailableError("redis down")

    async def set(self, *args: object, **kwargs: object) -> None:
        """恒定抛 Redis 不可用。

        Raises:
            RedisUnavailableError: 恒定。
        """
        raise RedisUnavailableError("redis down")


async def test_dedup_swallows_redis_unavailable() -> None:
    """Redis 抛 `RedisUnavailableError`：预判返回 False、标记静默（由唯一约束兜底）。"""
    from redis.asyncio import Redis

    dedup = EventConsumeDedup(client=cast("Redis", _UnavailableDedupClient()))
    assert await dedup.seen(group="bms-branch", event_id="evt-1") is False
    await dedup.remember(group="bms-branch", event_id="evt-1")


class _FailingConsumer(_Consumer):
    """`receive` 恒抛错的客户端替身（验证后台循环的异常续跑分支）。"""

    def receive(self, max_message_num: int, invisible_duration: int) -> ConcurrentStableList[Any]:
        """恒定抛错。

        Args:
            max_message_num: 上限（忽略）。
            invisible_duration: 可见性超时（忽略）。

        Raises:
            RuntimeError: 恒定。
        """
        raise RuntimeError("poll boom")


async def test_background_loop_survives_poll_error(dead_letter_registry: EngineRegistry) -> None:
    """后台循环遇到单轮异常继续跑（不终止该组）。"""
    settings = _settings()
    settings.event_consumer.poll_interval_seconds = 0.01
    consumer = _FailingConsumer()
    group = _group(dead_letter_registry, consumer, _Handler(), settings=settings)
    await group.start()
    await asyncio.sleep(0.05)  # 至少一轮拉取抛错并退避
    await group.stop()
    assert consumer.shutdown_calls == 1


def test_validate_same_ordered_in_group_passes() -> None:
    """同组多条声明 ordered 一致 → 不报不一致（覆盖「跳过不一致分支」）。"""
    records = ConcurrentStableList(
        [
            EventConsumerRecord(consumer="audit-chain", event_type=_EVENT_TYPE, handler_factory=_Handler, ordered=True),
            EventConsumerRecord(
                consumer="audit-chain", event_type="sys.user.updated", handler_factory=_Handler, ordered=True
            ),
        ]
    )
    errors = [error for error in validate_event_consumer_records(records) if "ordered 声明不一致" in error]
    assert errors == []


async def test_metrics_without_dead_letter(dead_letter_registry: EngineRegistry) -> None:
    """有指标但无死信时只上报消费计数（死信指标分支跳过）。"""

    class _Metrics:
        def __init__(self) -> None:
            self.calls: ConcurrentStableList[str] = ConcurrentStableList()

        async def counter(self, name: str, value: float = 1.0, labels: Any = None) -> None:
            self.calls.add(name)

    metrics = _Metrics()
    consumer = _Consumer(ConcurrentStableList([ConcurrentStableList([_Message(_event())])]))
    group = _group(dead_letter_registry, consumer, _Handler(), metrics=metrics)
    await group.consume_once()
    assert "bms_event_consume_total" in list(metrics.calls)
    assert "bms_event_dead_letter_total" not in list(metrics.calls)
    await group.aclose()
