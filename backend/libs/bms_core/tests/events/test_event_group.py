"""消费组运行时护栏：端口契约、处理器分轨与占位实现。

依据《详细设计 · 事件总线》§4.3：消费组是装配端口（`event_consumer`），处理器是 `event_handler`
轨（不进装配）；`[event_consumer].provider` 为空时占位实现只装载声明、不启动、不拉取——保证
「未部署 broker 的服务启动行为与引入消费组之前完全一致」。
"""

import inspect

import pytest

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.events.base import (
    BaseEventConsumer,
    BaseEventConsumerGroup,
    ConsumedTally,
    EventConsumer,
)
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.null import NullEventConsumer, NullEventConsumerGroup


class _Handler(EventConsumer):
    """测试处理器。"""

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return "sys.user.created"

    async def consume(self, event: object) -> None:
        """消费事件（测试空实现）。

        Args:
            event: 事件信封。
        """


def _factory() -> _Handler:
    """处理器工厂。"""
    return _Handler()


def _record(consumer: str = "audit.chain", event_type: str = "sys.user.created") -> EventConsumerRecord:
    """构造一条声明。

    Args:
        consumer: 组名。
        event_type: 事件类型。

    Returns:
        EventConsumerRecord: 声明。
    """
    return EventConsumerRecord(consumer=consumer, event_type=event_type, handler_factory=_factory)


def test_group_port_is_abstract() -> None:
    """组端口是抽象契约（不得直接实例化）。"""
    assert inspect.isabstract(BaseEventConsumerGroup)
    assert issubclass(NullEventConsumerGroup, BaseEventConsumerGroup)
    assert issubclass(NullEventConsumerGroup, BaseAsyncResource)


def test_group_port_key() -> None:
    """组占装配域 `event_consumer`；处理器独立成 `event_handler` 轨（不参与装配）。"""
    assert BaseEventConsumerGroup.key == "event_consumer"
    assert BaseEventConsumerGroup.plugin_key == "event_consumer"
    assert BaseEventConsumer.key == "event_handler"
    assert BaseEventConsumer.plugin_key == "event_handler"


def test_null_group_disabled_by_default() -> None:
    """占位组默认不启用（不拉取）。"""
    assert NullEventConsumerGroup().enabled is False


def test_null_group_loads_records_without_starting() -> None:
    """装载声明可查、可派生订阅；重复装载去重。"""
    group = NullEventConsumerGroup()
    group.load(ConcurrentStableList([_record(), _record()]))
    assert len(group.records) == 1
    subscriptions = group.subscriptions()
    assert [(item.consumer, item.event_type) for item in subscriptions] == [("audit.chain", "sys.user.created")]


def test_null_group_load_keeps_multiple_event_types() -> None:
    """同组不同事件各成一条订阅。"""
    group = NullEventConsumerGroup()
    group.load(ConcurrentStableList([_record(), _record(event_type="sys.user.updated")]))
    assert len(group.subscriptions()) == 2


async def test_null_group_consume_once_returns_empty_tally() -> None:
    """占位组单轮消费返回空汇总（不拉取、不消费）。"""
    group = NullEventConsumerGroup()
    group.load(ConcurrentStableList([_record()]))
    tally = await group.consume_once()
    assert tally.received == 0
    assert tally.succeeded == 0


async def test_null_group_start_stop_are_noops() -> None:
    """占位组启停为空操作，可重复调用。"""
    group = NullEventConsumerGroup()
    await group.start()
    await group.stop()
    await group.aclose()
    assert group.enabled is False


async def test_null_consumer_consume_is_noop() -> None:
    """处理器占位实现消费为空操作。"""
    consumer = NullEventConsumer()
    assert consumer.event_type == "event.null"
    assert await consumer.consume(None) is None  # type: ignore[arg-type]


def test_consumed_tally_merge() -> None:
    """消费汇总合并用于多组累加（积压以外的计数项逐项相加）。"""
    merged = ConsumedTally(received=3, succeeded=1).merge(ConsumedTally(received=2, dead=1, skipped=1))
    assert merged.received == 5
    assert merged.succeeded == 1
    assert merged.dead == 1
    assert merged.skipped == 1
    assert merged.retried == 0


@pytest.mark.parametrize("field", ConsumedTally.COUNT_FIELDS)
def test_consumed_tally_fields_are_zero_by_default(field: str) -> None:
    """计数项缺省为 0（空汇总不产生假数据）。"""
    assert getattr(ConsumedTally(), field) == 0
