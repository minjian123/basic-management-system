"""events 能力域缺省实现（Null Object）：发布 / 消费空操作（05 补缺；真实实现随阶段十 M10 集成消息可用）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.events.base import EventConsumer, EventEnvelope, EventPublisher

__all__ = ["NullEventConsumer", "NullEventPublisher"]

NULL_EVENT_TYPE = "event.null"


class NullEventPublisher(EventPublisher, BaseNullObject):
    """占位事件发布：空操作（不连消息中间件、不投递；真实实现随阶段十 M10 集成消息可用）。"""

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
    """占位事件消费：空操作（不连消息中间件、不消费；真实实现随阶段十 M10 集成消息可用）。

    分轨后实现名沿用约定的 `null`（`NULL_PLUGIN_NAME`），与发布侧不冲突。
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
