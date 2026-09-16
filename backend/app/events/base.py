"""事件能力域：事件发布 / 消费基座契约（消息中间件在阶段十 M10 集成消息可用回补）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.plugin import (
    DEFAULT_CONTRACT_VERSION,
    NULL_PLUGIN_NAME,
    BasePluggable,
    resolve_plugin,
)


@dataclass
class EventEnvelope(BaseObject):
    """事件信封：统一事件载体（类型 + 负载 + 租户 + 链路标识）。"""

    event_type: str
    payload: dict[str, object] = field(default_factory=dict[str, object])
    tenant_id: str | None = None
    trace_id: str | None = None


class BaseEventWorker(BasePluggable, ABC):
    """事件工作单元契约：发布 / 消费共享的事件类型（插件化中间层，02-1 迁入）。"""

    key: str = "event"
    plugin_key: str = "event"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def event_type(self) -> str:
        """事件类型（发布主题 / 订阅类型）。"""


class BaseEventPublisher(BaseEventWorker):
    """发布侧基类（共享父 `BaseEventWorker` 之下的层）：能力域键沿用 `event`。"""

    key: str = "event"
    plugin_key: str = "event"


class EventPublisher(BaseEventPublisher):
    """事件发布基座契约：统一异步发布接口（事务消息回补）。"""

    @abstractmethod
    async def publish(self, event: EventEnvelope) -> None:
        """发布事件（至少一次投递）。

        Args:
            event: 事件信封。
        """

    @abstractmethod
    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布（本地事务与消息一致，RocketMQ 回补）。

        Args:
            event: 事件信封。
        """


class BaseEventConsumer(BaseEventWorker):
    """消费侧基类（共享父 `BaseEventWorker` 之下的层）：与发布侧**分轨**，独立能力域键 `event_consumer`。

    作为独立端口，三属性自身声明（与 `BaseEventWorker` 同口径）。
    """

    key: str = "event_consumer"
    plugin_key: str = "event_consumer"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION


class EventConsumer(BaseEventConsumer):
    """事件消费基座契约：分区有序异步消费（真实实现随阶段十 M10 集成消息可用）。"""

    @abstractmethod
    async def consume(self, event: EventEnvelope) -> None:
        """消费事件（分区内有序）。

        Args:
            event: 事件信封。
        """


def get_event_publisher(request: Request) -> EventPublisher:
    """依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

    Args:
        request: 应用请求（取装配 settings）。

    Returns:
        EventPublisher: 应用装配的事件发布实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "EventPublisher",
        resolve_plugin(
            "event",
            settings.event.provider,
            expected_version=EventPublisher.contract_version,
        ),
    )
