"""消费死信落库：消费失败超限后写 `sys_event_dead_letter`（`source = consumer`）。

- **统一落平台库**：死信看板接口 `GET /api/v1/outbox/dead-letters` 读平台库；落各租户库则看板聚合不到。
- **独立事务**：不挂在消费者业务事务上——业务回滚不能让死信记录一起消失。
- **落库失败不吞消息**：调用方（消费组）在落库失败时不 ack，让 broker 重投；宁可重复不可丢。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.models.outbox import SysEventDeadLetter
from bms_core.outbox.base import DEAD_LETTER_SOURCE_CONSUMER, ERROR_MSG_MAX_LENGTH

__all__ = ["EventDeadLetterEntry", "EventDeadLetterRecorder"]

_LOGGER = get_logger("bms")


@dataclass(frozen=True)
class EventDeadLetterEntry(BaseValueObject):
    """消费死信记录（落库入参）。

    Attributes:
        consumer: 消费组名（`source = consumer` 时的处置归属）。
        event_id: 事件 ID（幂等键）。
        event_type: 事件类型。
        error_msg: 失败原因（落库截断 512）。
        payload: 事件负载（排障 / 重投依据）。
        aggregate_key: 聚合 / 分区键。
        tenant_id: 租户主键（雪花 id 十进制字符串）。
        retry_count: 转入死信前的已重试次数。
        occurred_at: 事件发生时间（UTC）。
    """

    consumer: str
    event_id: str
    event_type: str
    error_msg: str
    payload: ConcurrentStableFrozenDict[str, object] = field(default_factory=ConcurrentStableFrozenDict[str, object])
    aggregate_key: str | None = None
    tenant_id: str | None = None
    retry_count: int = 0
    occurred_at: datetime | None = None


class EventDeadLetterRecorder(BaseFrameworkObject):
    """消费死信写入器（平台库独立事务）。"""

    def __init__(self, *, engine_registry: EngineRegistry, session_factory: SessionFactory | None = None) -> None:
        """初始化。

        Args:
            engine_registry: 引擎注册表（按库键开会话）。
            session_factory: 异步会话工厂（缺省由会话入口新建）。
        """
        self._engine_registry = engine_registry
        self._session_factory = session_factory

    async def record(self, entry: EventDeadLetterEntry) -> None:
        """写入一条消费死信（独立事务提交）。

        Args:
            entry: 死信记录。

        Raises:
            Exception: 落库失败原样上抛——调用方据此不 ack，让 broker 重投（不静默丢消息）。
        """
        async with (
            session_scope(self._engine_registry, db_key=PLATFORM_DB_KEY, factory=self._session_factory) as session,
            session.begin(),
        ):
            session.add(
                SysEventDeadLetter(
                    source=DEAD_LETTER_SOURCE_CONSUMER,
                    event_id=entry.event_id,
                    event_type=entry.event_type,
                    consumer=entry.consumer,
                    aggregate_key=entry.aggregate_key,
                    tenant_id=_tenant_id_col(entry.tenant_id),
                    payload=ConcurrentStableDict(entry.payload),
                    error_msg=entry.error_msg[:ERROR_MSG_MAX_LENGTH],
                    retry_count=entry.retry_count,
                    occurred_at=entry.occurred_at or datetime.now(UTC).replace(tzinfo=None),
                )
            )
            await session.flush()
        _LOGGER.error(
            "event_dead_letter",
            consumer=entry.consumer,
            event_id=entry.event_id,
            event_type=entry.event_type,
            retry_count=entry.retry_count,
            error=entry.error_msg[:200],
        )

    async def record_many(self, entries: ConcurrentStableList[EventDeadLetterEntry]) -> None:
        """批量写入死信（同一事务；单条失败整体回滚，由调用方按未 ack 处理）。

        Args:
            entries: 死信记录清单。
        """
        if not entries:
            return
        async with (
            session_scope(self._engine_registry, db_key=PLATFORM_DB_KEY, factory=self._session_factory) as session,
            session.begin(),
        ):
            for entry in entries:
                session.add(
                    SysEventDeadLetter(
                        source=DEAD_LETTER_SOURCE_CONSUMER,
                        event_id=entry.event_id,
                        event_type=entry.event_type,
                        consumer=entry.consumer,
                        aggregate_key=entry.aggregate_key,
                        tenant_id=_tenant_id_col(entry.tenant_id),
                        payload=ConcurrentStableDict(entry.payload),
                        error_msg=entry.error_msg[:ERROR_MSG_MAX_LENGTH],
                        retry_count=entry.retry_count,
                        occurred_at=entry.occurred_at or datetime.now(UTC).replace(tzinfo=None),
                    )
                )
            await session.flush()
        for entry in entries:
            _LOGGER.error(
                "event_dead_letter",
                consumer=entry.consumer,
                event_id=entry.event_id,
                event_type=entry.event_type,
                retry_count=entry.retry_count,
                error=entry.error_msg[:200],
            )


def _tenant_id_col(tenant_id: str | None) -> int | None:
    """信封租户位 → 主键列值（空保持空；非十进制视为无租户并告警）。

    Args:
        tenant_id: 租户主键（雪花 id 十进制字符串）。

    Returns:
        int | None: 主键列值。
    """
    if not tenant_id:
        return None
    try:
        return int(tenant_id)
    except ValueError:
        _LOGGER.warning("event_dead_letter_bad_tenant", tenant_id=tenant_id)
        return None
