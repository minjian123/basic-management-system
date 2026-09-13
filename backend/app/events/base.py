"""事件能力域：事件发布 / 消费基座契约（消息中间件在阶段八回补）。"""

from abc import abstractmethod
from dataclasses import dataclass, field

from app.core.base import BaseObject
from app.core.capability import BaseEventWorker


@dataclass
class EventEnvelope(BaseObject):
    """事件信封：统一事件载体（类型 + 负载 + 链路标识）。"""

    event_type: str
    payload: dict[str, object] = field(default_factory=dict[str, object])
    trace_id: str | None = None


class EventPublisher(BaseEventWorker):
    """事件发布基座契约：统一发布接口（事务消息回补）。"""

    @abstractmethod
    def publish(self, event: EventEnvelope) -> None:
        """发布事件（至少一次投递）。

        Args:
            event: 事件信封。
        """

    @abstractmethod
    def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布（本地事务与消息一致，RocketMQ 回补）。

        Args:
            event: 事件信封。
        """


class EventConsumer(BaseEventWorker):
    """事件消费基座契约：分区有序消费（回补系统集成与消息阶段）。"""

    @abstractmethod
    def consume(self, event: EventEnvelope) -> None:
        """消费事件（分区内有序）。

        Args:
            event: 事件信封。
        """
