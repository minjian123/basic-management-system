"""事务性发件箱与幂等消费能力域：发件箱存储 / 投递器契约与提供者。

- **发件箱存储** `BaseOutboxStore`（插件键 `outbox_store`）：业务事务内**同库同事务**写事件
  （`enqueue`，flush 不提交）；投递器读取待投递（`claim_pending`，按 `(aggregate_key, id)`
  同聚合仅取队首）并按结果标记（`mark_delivered` / `mark_failed`，失败指数退避、超限转死信）；
  并发件箱作事件账本支持 `replay`；死信看板经 `list_dead_letters` / `get_dead_letter` /
  `set_dead_letter_status` 读写。
- **投递器** `BaseOutboxDispatcher`（插件键 `outbox_dispatcher`，异步资源）：轮询发件箱，
  经事件发布端口 `EventPublisher` 转发（业务代码不直连 MQ）；`enabled` 时后台轮询。
- 配置分区：`[outbox_store]`（存储）/ `[outbox]`（投递器，含轮询参数）。
- 缺省实现 `NullOutboxStore` / `NullOutboxDispatcher`（无副作用）。
- 提供者 `get_outbox_store` / `get_outbox_dispatcher`（应用级单例）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseAsyncResource
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope

OUTBOX_STATUS_PENDING = "pending"
"""待投递。"""

OUTBOX_STATUS_DELIVERED = "delivered"
"""已投递。"""

OUTBOX_STATUS_DEAD = "dead"
"""投递失败转死信。"""

OUTBOX_STATUSES: tuple[str, ...] = (OUTBOX_STATUS_PENDING, OUTBOX_STATUS_DELIVERED, OUTBOX_STATUS_DEAD)
"""发件箱状态清单。"""

DEAD_LETTER_STATUS_PENDING = "pending"
"""死信待处置。"""

DEAD_LETTER_STATUS_REPLAYED = "replayed"
"""死信已重投。"""

DEAD_LETTER_STATUS_IGNORED = "ignored"
"""死信已忽略。"""

DEAD_LETTER_STATUSES: tuple[str, ...] = (
    DEAD_LETTER_STATUS_PENDING,
    DEAD_LETTER_STATUS_REPLAYED,
    DEAD_LETTER_STATUS_IGNORED,
)
"""死信处置状态清单。"""

DEAD_LETTER_SOURCE_OUTBOX = "outbox"
"""死信来源：投递失败。"""

DEAD_LETTER_SOURCE_CONSUMER = "consumer"
"""死信来源：消费失败。"""

DEAD_LETTER_SOURCES: tuple[str, ...] = (DEAD_LETTER_SOURCE_OUTBOX, DEAD_LETTER_SOURCE_CONSUMER)
"""死信来源清单。"""

DEFAULT_BATCH_SIZE = 100
"""单轮单库取待投递上限。"""

DEFAULT_MAX_RETRIES = 5
"""转死信前的最大重试次数。"""

DEFAULT_RETRY_BACKOFF_SECONDS = 1.0
"""指数退避基数（秒）：`backoff × 2^(retry_count-1)`。"""

ORDER_SCAN_FACTOR = 10
"""取待投递扫描放大倍数（先按 `limit×factor` 取候选，再按聚合分组取队首）。"""

ERROR_MSG_MAX_LENGTH = 512
"""失败原因落库截断长度（对齐列宽）。"""


@dataclass(frozen=True)
class OutboxRecord(BaseObject):
    """发件箱记录（投递器按此重建事件信封并投递）。"""

    event_id: str
    """事件 ID（幂等键）。"""
    event_type: str
    """事件类型（`{域}.{对象}.{动作}`）。"""
    aggregate_key: str | None
    """聚合 / 分区键（同聚合按序投递；空 = 独立事件）。"""
    tenant_id: str | None
    """租户标识。"""
    payload: dict[str, object]
    """事件负载。"""
    occurred_at: datetime
    """事件发生时间（UTC）。"""
    status: str
    """投递状态。"""
    retry_count: int
    """已重试次数。"""
    next_retry_at: datetime | None = None
    """下次可投递时间（退避）。"""
    delivered_at: datetime | None = None
    """投递成功时间（UTC）。"""
    error_msg: str | None = None
    """最近一次失败原因。"""

    def to_envelope(self) -> EventEnvelope:
        """重建事件信封（保真 `event_id` / `occurred_at` / `aggregate_key`）。

        Returns:
            EventEnvelope: 事件信封。
        """
        return EventEnvelope(
            event_type=self.event_type,
            payload=dict(self.payload),
            tenant_id=self.tenant_id,
            event_id=self.event_id,
            occurred_at=self.occurred_at,
            aggregate_key=self.aggregate_key,
        )


@dataclass(frozen=True)
class DeadLetterRecord(BaseObject):
    """死信记录（看板读写）。"""

    id: int
    """主键。"""
    source: str
    """来源（`outbox` / `consumer`）。"""
    event_id: str
    """事件 ID。"""
    event_type: str
    """事件类型。"""
    consumer: str | None
    """消费者标识。"""
    aggregate_key: str | None
    """聚合 / 分区键。"""
    tenant_id: str | None
    """租户标识。"""
    payload: dict[str, object]
    """事件负载。"""
    error_msg: str
    """失败原因。"""
    retry_count: int
    """转入死信前的已重试次数。"""
    status: str
    """处置状态（`pending` / `replayed` / `ignored`）。"""
    occurred_at: datetime
    """事件发生时间（UTC）。"""


@dataclass(frozen=True)
class DispatchResult(BaseObject):
    """单次投递汇总。"""

    published: int = 0
    """投递成功条数。"""
    failed: int = 0
    """投递失败条数（含转死信）。"""
    dead: int = 0
    """本轮转死信条数。"""
    backlog: int = 0
    """处理后的待投递积压。"""

    def merge(self, other: DispatchResult) -> DispatchResult:
        """合并两次投递汇总（多库轮询）。

        Args:
            other: 另一次投递汇总。

        Returns:
            DispatchResult: 合并结果。
        """
        return DispatchResult(
            published=self.published + other.published,
            failed=self.failed + other.failed,
            dead=self.dead + other.dead,
            backlog=other.backlog,
        )


class BaseOutboxStore(BasePluggable, ABC):
    """发件箱存储契约：同库同事务写入 + 待投递读取 + 标记 + 重放 + 死信看板读写。"""

    key: str = "outbox_store"
    plugin_key: str = "outbox_store"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def enqueue(self, session: DbSession, event: EventEnvelope) -> str:
        """在业务事务内写发件箱（flush 不提交；缺省补齐 event_id / occurred_at）。

        Args:
            session: 业务事务会话（与业务数据同事务）。
            event: 事件信封。

        Returns:
            str: 事件 ID。
        """

    @abstractmethod
    async def claim_pending(self, session: DbSession, *, now: datetime, limit: int) -> list[OutboxRecord]:
        """取待投递事件（按 `(aggregate_key, id)` 同聚合仅队首、到期者）。

        Args:
            session: 会话。
            now: 当前时间（UTC）。
            limit: 返回上限。

        Returns:
            list[OutboxRecord]: 待投递记录。
        """

    @abstractmethod
    async def mark_delivered(self, session: DbSession, event_id: str) -> None:
        """标记已投递。

        Args:
            session: 会话。
            event_id: 事件 ID。
        """

    @abstractmethod
    async def mark_failed(
        self,
        session: DbSession,
        event_id: str,
        error: str,
        *,
        max_retries: int,
        backoff: float,
    ) -> bool:
        """标记投递失败（指数退避；超 `max_retries` 转死信）。

        Args:
            session: 会话。
            event_id: 事件 ID。
            error: 失败原因。
            max_retries: 转死信前的最大重试次数。
            backoff: 退避基数（秒）。

        Returns:
            bool: 已转死信 True（仍待重试 False）。
        """

    @abstractmethod
    async def replay(
        self,
        session: DbSession,
        *,
        event_id: str | None = None,
        event_type: str | None = None,
        aggregate_key: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> int:
        """重放：把已投递 / 死信事件重置为待投递（消费端幂等，重放安全）。

        Args:
            session: 会话。
            event_id: 事件 ID 精确筛选（死信重投）。
            event_type: 事件类型筛选。
            aggregate_key: 聚合键筛选。
            since: 发生时间下限（UTC）。
            limit: 重置上限。

        Returns:
            int: 重置条数。
        """

    @abstractmethod
    async def list_dead_letters(
        self,
        session: DbSession,
        *,
        status: str | None = None,
        source: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[DeadLetterRecord], int]:
        """死信列表（按 `id` 倒序 + 筛选 + 分页）。

        Args:
            session: 会话。
            status: 处置状态筛选。
            source: 来源筛选。
            offset: 偏移。
            limit: 上限。

        Returns:
            tuple[list[DeadLetterRecord], int]: （记录列表，总数）。
        """

    @abstractmethod
    async def get_dead_letter(self, session: DbSession, dead_letter_id: int) -> DeadLetterRecord | None:
        """取单条死信。

        Args:
            session: 会话。
            dead_letter_id: 死信主键。

        Returns:
            DeadLetterRecord | None: 记录；不存在 None。
        """

    @abstractmethod
    async def set_dead_letter_status(self, session: DbSession, dead_letter_id: int, status: str) -> bool:
        """设置死信处置状态。

        Args:
            session: 会话。
            dead_letter_id: 死信主键。
            status: 目标状态（`replayed` / `ignored`）。

        Returns:
            bool: 命中 True；不存在 False。
        """

    @abstractmethod
    async def backlog(self, session: DbSession) -> int:
        """待投递积压数。

        Args:
            session: 会话。

        Returns:
            int: 待投递条数。
        """


class BaseOutboxDispatcher(BasePluggable, BaseAsyncResource, ABC):
    """投递器契约：轮询发件箱、经事件发布端口转发并标记（异步资源，可后台轮询）。"""

    key: str = "outbox_dispatcher"
    plugin_key: str = "outbox_dispatcher"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """后台轮询是否启用。"""

    @abstractmethod
    async def dispatch_once(self, *, db_key: str) -> DispatchResult:
        """对单个库执行一次投递。

        Args:
            db_key: 数据源键。

        Returns:
            DispatchResult: 投递汇总。
        """

    @abstractmethod
    async def dispatch_due(self) -> DispatchResult:
        """对目标库集合各执行一次投递。

        Returns:
            DispatchResult: 汇总结果。
        """


def get_outbox_store(request: Request) -> BaseOutboxStore:
    """取应用级发件箱存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOutboxStore: 应用装配的发件箱存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOutboxStore",
        resolve_plugin(
            "outbox_store",
            settings.outbox_store.provider,
            expected_version=BaseOutboxStore.contract_version,
        ),
    )


def get_outbox_dispatcher(request: Request) -> BaseOutboxDispatcher:
    """取应用级投递器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseOutboxDispatcher: 应用装配的投递器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseOutboxDispatcher",
        resolve_plugin(
            "outbox_dispatcher",
            settings.outbox.provider,
            expected_version=BaseOutboxDispatcher.contract_version,
        ),
    )
