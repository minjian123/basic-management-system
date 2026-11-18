"""死信待处置统计护栏（15_01）：按来源分组 / 只计 pending / 最老发生时间 / 占位空集。"""

from datetime import datetime
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventDeadLetter
from bms_core.outbox.base import (
    DEAD_LETTER_SOURCE_CONSUMER,
    DEAD_LETTER_SOURCE_OUTBOX,
    DEAD_LETTER_STATUS_IGNORED,
    DEAD_LETTER_STATUS_PENDING,
    DEAD_LETTER_STATUS_REPLAYED,
)
from bms_core.outbox.null import NullOutboxStore
from bms_core.outbox.store import SqlOutboxStore

pytestmark = pytest.mark.kiwi_id(2531)

_OLDEST = datetime(2026, 11, 17, 8, 0, 0)
_NEWER = datetime(2026, 11, 18, 9, 0, 0)
_OLDER_THAN_OLDEST = datetime(2026, 11, 10, 0, 0, 0)


async def _session() -> AsyncSession:
    """进程内 SQLite 会话（只建死信表）。"""
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[cast("Table", SysEventDeadLetter.__table__)])
    return async_sessionmaker(engine, expire_on_commit=False)()


def _row(source: str, status: str, occurred_at: datetime, event_id: str) -> SysEventDeadLetter:
    """构造一条死信行（字段齐备）。"""
    return SysEventDeadLetter(
        source=source,
        event_id=event_id,
        event_type="sys.data.changed",
        consumer="audit-chain" if source == DEAD_LETTER_SOURCE_CONSUMER else None,
        aggregate_key="tenant:1001",
        tenant_id=1001,
        payload=ConcurrentStableDict({"tenant_id": "1001"}),
        error_msg="boom",
        retry_count=3,
        status=status,
        occurred_at=occurred_at,
    )


async def test_stats_group_by_source_and_only_pending() -> None:
    """按来源分组、只统计 pending、最老时间取该来源最小值。"""
    session = await _session()
    session.add_all(
        [
            _row(DEAD_LETTER_SOURCE_OUTBOX, DEAD_LETTER_STATUS_PENDING, _OLDEST, "o1"),
            _row(DEAD_LETTER_SOURCE_OUTBOX, DEAD_LETTER_STATUS_PENDING, _NEWER, "o2"),
            _row(DEAD_LETTER_SOURCE_OUTBOX, DEAD_LETTER_STATUS_REPLAYED, _OLDER_THAN_OLDEST, "o3"),
            _row(DEAD_LETTER_SOURCE_CONSUMER, DEAD_LETTER_STATUS_PENDING, _NEWER, "c1"),
            _row(DEAD_LETTER_SOURCE_CONSUMER, DEAD_LETTER_STATUS_IGNORED, _OLDER_THAN_OLDEST, "c2"),
        ]
    )
    await session.commit()

    stats = await SqlOutboxStore().dead_letter_stats(session)
    assert [(stat.source, stat.pending) for stat in stats] == [
        (DEAD_LETTER_SOURCE_CONSUMER, 1),
        (DEAD_LETTER_SOURCE_OUTBOX, 2),
    ]
    assert stats[0].oldest_occurred_at == _NEWER
    assert stats[1].oldest_occurred_at == _OLDEST
    await session.aclose()


async def test_stats_empty_when_no_pending() -> None:
    """无待处置时返回空集（不返回 0 值行，指标侧据此写 0）。"""
    session = await _session()
    session.add(_row(DEAD_LETTER_SOURCE_OUTBOX, DEAD_LETTER_STATUS_REPLAYED, _OLDEST, "o1"))
    await session.commit()
    assert list(await SqlOutboxStore().dead_letter_stats(session)) == []
    await session.aclose()


async def test_null_store_returns_empty() -> None:
    """占位存储恒定空集（不改变既有语义）。"""
    session = await _session()
    assert list(await NullOutboxStore().dead_letter_stats(session)) == []
    await session.aclose()
