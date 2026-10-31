"""events 能力域缺省实现（Null Object）：发布 / 消费空操作（真实实现随后续批次回补）。

- `NullEventPublisher` / `NullEventConsumer`：发布 / 处理器占位（无副作用）。
- `NullEventConsumerGroup`：消费组运行时占位——**只装载声明、不启动、不拉取**；`[event_consumer].provider`
  为空时行为与引入消费组之前完全一致（既有用例零影响）。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.events.base import (
    BaseEventConsumerGroup,
    ConsumedTally,
    EventConsumer,
    EventEnvelope,
    EventPublisher,
)
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.contracts import EventSubscription

__all__ = ["NULL_EVENT_TYPE", "NullEventConsumer", "NullEventConsumerGroup", "NullEventPublisher"]

NULL_EVENT_TYPE = "event.null"


class NullEventPublisher(EventPublisher, BaseNullObject):
    """占位事件发布：空操作（不连消息中间件、不投递；真实实现待消息中间件就绪后回补）。"""

    @property
    def event_type(self) -> str:
        """事件类型（占位固定 `event.null`）。

        Returns:
            str: 占位事件类型。
        """
        return NULL_EVENT_TYPE

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件（占位空操作）。

        Args:
            event: 事件信封（占位忽略）。
        """

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布（占位空操作）。

        Args:
            event: 事件信封（占位忽略）。
        """


class NullEventConsumer(EventConsumer, BaseNullObject):
    """占位事件处理器：空操作（不处理任何事件）。

    分轨后处理器域键为 `event_handler`，与消费组端口（`event_consumer`）不冲突。
    """

    @property
    def event_type(self) -> str:
        """事件类型（占位固定 `event.null`）。

        Returns:
            str: 占位事件类型。
        """
        return NULL_EVENT_TYPE

    async def consume(self, event: EventEnvelope) -> None:
        """消费事件（占位空操作）。

        Args:
            event: 事件信封（占位忽略）。
        """


class NullEventConsumerGroup(BaseEventConsumerGroup, BaseNullObject):
    """占位消费组运行时：装载声明但不启动、不拉取（无 broker 环境与测试缺省）。"""

    def __init__(self) -> None:
        """初始化空声明清单。"""
        self._records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()

    @property
    def enabled(self) -> bool:
        """消费是否启用（占位恒 False）。

        Returns:
            bool: 恒 False。
        """
        return False

    @property
    def records(self) -> ConcurrentStableList[EventConsumerRecord]:
        """已装载的组声明（只读视图，供诊断与测试核对）。

        Returns:
            ConcurrentStableList[EventConsumerRecord]: 声明清单。
        """
        return self._records

    def load(self, records: ConcurrentStableList[EventConsumerRecord]) -> None:
        """装载声明（占位：仅记录，不启动）。

        Args:
            records: 组声明清单。
        """
        for record in records:
            if record not in self._records:
                self._records.add(record)

    def subscriptions(self) -> ConcurrentStableList[EventSubscription]:
        """由声明派生订阅清单（占位实现同样返回，便于校验链路一致）。

        Returns:
            ConcurrentStableList[EventSubscription]: 订阅声明。
        """
        return ConcurrentStableList(
            EventSubscription(
                consumer=record.consumer,
                event_type=record.event_type,
                description=record.description,
            )
            for record in self._records
        )

    async def consume_once(self, *, max_messages: int = 32) -> ConsumedTally:
        """单轮消费（占位：不拉取）。

        Args:
            max_messages: 单组单轮拉取上限（占位忽略）。

        Returns:
            ConsumedTally: 空汇总。
        """
        return ConsumedTally()

    async def start(self) -> None:
        """启动后台消费（占位空操作）。"""

    async def stop(self) -> None:
        """停止后台消费（占位空操作）。"""
