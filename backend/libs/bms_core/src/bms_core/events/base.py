"""事件能力域：事件发布 / 消费基座契约（消息中间件就绪后回补真实实现）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, cast

from fastapi import Request

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.objects import BaseDataContract, BaseTallyContract
from bms_core.core.plugin import (
    DEFAULT_CONTRACT_VERSION,
    NULL_PLUGIN_NAME,
    BasePluggable,
    resolve_plugin,
)

if TYPE_CHECKING:
    from bms_core.events.consumer_records import EventConsumerRecord
    from bms_core.events.contracts import EventSubscription

DEFAULT_EVENT_VERSION = "1.0.0"
"""事件契约缺省版本（未登记契约时回落；登记契约取契约版本，见 `events/contracts.py`）。"""

DEFAULT_CONSUME_BATCH = 32
"""单轮消费拉取上限（`[event_consumer].batch_size` 缺省）。"""


@dataclass
class EventEnvelope(BaseDataContract):
    """事件信封：统一事件载体（幂等键 + 类型 + 负载 + 租户 + 链路标识 + 聚合键 + 契约版本）。

    - `event_id`：幂等键（消费端去重）；缺省由事务性发件箱写入时生成。
    - `occurred_at`：事件发生时间（UTC）；缺省由发件箱写入时取当前时刻。
    - `aggregate_key`：聚合 / 分区键（同聚合按序投递）；空 = 独立事件。
    - `event_version`：事件契约版本（`X.Y.Z`）；缺省由发件箱按登记契约补齐（未登记回落
      `DEFAULT_EVENT_VERSION`），投递时经发件箱账本保真（消费方按主版本兼容）。
    - `tenant_id`：租户主键（雪花 id 十进制字符串；与请求上下文 / 令牌租户位同源）；
      平台链 / 审计等无租户事件为空。
    """

    event_type: str
    payload: ConcurrentStableDict[str, object] = field(default_factory=ConcurrentStableDict[str, object])
    tenant_id: str | None = None
    trace_id: str | None = None
    event_id: str | None = None
    occurred_at: datetime | None = None
    aggregate_key: str | None = None
    event_version: str | None = None


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
    """消费侧**处理器**基类：与发布侧分轨，独立能力域键 `event_handler`（不参与插件装配）。

    处理器是「一个事件类型 → 一段处理逻辑」的单元，由消费组按声明装配；组运行时可替换
    （`event_consumer` 域），处理器契约不变。
    """

    key: str = "event_handler"
    plugin_key: str = "event_handler"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION


class EventConsumer(BaseEventConsumer):
    """事件处理器契约：分区内按 key 串行调用（顺序由消费组保证）。"""

    @abstractmethod
    async def consume(self, event: EventEnvelope) -> None:
        """消费事件（分区内有序）。

        Args:
            event: 事件信封。
        """


@dataclass(frozen=True)
class ConsumedTally(BaseTallyContract):
    """单轮 / 单组消费汇总（计数契约，供诊断命令与指标上报）。"""

    COUNT_FIELDS: ClassVar[ConcurrentStableFrozenList[str]] = ConcurrentStableFrozenList(
        ("received", "succeeded", "retried", "dead", "skipped")
    )

    received: int = 0
    """拉取到的消息数。"""
    succeeded: int = 0
    """处理成功数。"""
    retried: int = 0
    """处理失败但仍可重试数（未 ack，等 broker 重投）。"""
    dead: int = 0
    """转入死信数（含毒消息）。"""
    skipped: int = 0
    """幂等命中跳过数。"""

    def merge(self, other: ConsumedTally) -> ConsumedTally:
        """合并两次汇总（多组累加）。

        Args:
            other: 另一次汇总。

        Returns:
            ConsumedTally: 合并结果。
        """
        return ConsumedTally(
            received=self.received + other.received,
            succeeded=self.succeeded + other.succeeded,
            retried=self.retried + other.retried,
            dead=self.dead + other.dead,
            skipped=self.skipped + other.skipped,
        )


class BaseEventConsumerGroup(BasePluggable, BaseAsyncResource, ABC):
    """消费组运行时端口（插件键 `event_consumer`）：装载声明 → 订阅 → 拉取分发 → 幂等 / 重试 / 死信。

    - **声明归提供方**：各服务经 `BaseServiceApplicationFactory.event_consumer_records()` 自持，
      基座装配期 `load()` 统一装载（无进程级注册表）。
    - **处理器契约不变**：处理器仍是 `EventConsumer`（`event_type` + `consume`）。
    - **顺序**：`ordered=True` 的组（审计链组）同 key 全串行；其余组按 key 分道、道内串行、道间并发。
    """

    key: str = "event_consumer"
    plugin_key: str = "event_consumer"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """消费是否启用（`[event_consumer].enabled`；未启用时只装载不拉取）。"""

    @abstractmethod
    def load(self, records: ConcurrentStableList[EventConsumerRecord]) -> None:
        """装载消费组声明（装配期调用一次；重复装载按合并规则去重）。

        Args:
            records: 各服务自持的组声明。
        """

    @abstractmethod
    def subscriptions(self) -> ConcurrentStableList[EventSubscription]:
        """当前声明对应的订阅清单（供契约覆盖校验与启动日志）。

        Returns:
            ConcurrentStableList[EventSubscription]: 订阅声明。
        """

    @abstractmethod
    async def consume_once(self, *, max_messages: int = DEFAULT_CONSUME_BATCH) -> ConsumedTally:
        """对所有组执行一轮拉取消费（可测 / 可诊断；不依赖后台循环）。

        Args:
            max_messages: 单组单轮拉取上限。

        Returns:
            ConsumedTally: 汇总结果。
        """

    @abstractmethod
    async def start(self) -> None:
        """启动后台消费循环（幂等）。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止后台消费循环并等待在途完成（幂等）。"""


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
