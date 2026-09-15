"""events 能力域缺省实现（Null Object）：发布空操作（05 补缺；消费轨随阶段八）。"""

from app.core.capability import BaseNullObject
from app.events.base import EventEnvelope, EventPublisher

__all__ = ["NullEventPublisher"]


class NullEventPublisher(EventPublisher, BaseNullObject):
    """占位事件发布：空操作（不连消息中间件、不投递；消费轨随阶段八）。"""

    @property
    def event_type(self) -> str:
        """事件类型（占位固定 `event.null`）。

        Returns:
            str: 占位事件类型。
        """
        return "event.null"

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
