"""作业监控投影护栏（Kiwi 2386）：四条事件 upsert / 旧事件丢弃 / 终态覆盖。"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope
from bms_core.jobs.events import (
    JOB_COMPLETED_EVENT,
    JOB_PROGRESS_EVENT,
    JOB_STARTED_EVENT,
    JOB_SUBMITTED_EVENT,
)
from bms_core.models.base import Base
from bms_core.models.platform.job import SysJobMonitor
from bms_platform.domains.job.repositories.job import JobMonitorRepository
from bms_platform.domains.job.services.monitor import JobMonitorService

pytestmark = pytest.mark.kiwi_id(2386)

BASE = datetime(2026, 11, 1, 3, 0, 0)


async def _session(tmp_path: Path):
    """建监控表并开会话。

    Args:
        tmp_path: 临时目录。

    Returns:
        会话上下文管理器。
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'monitor.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[SysJobMonitor.__table__]))
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _event(event_type: str, at: datetime, **payload: object) -> EventEnvelope:
    """构造作业事件。

    Args:
        event_type: 事件类型。
        at: 发生时刻。
        **payload: 负载字段。

    Returns:
        EventEnvelope: 事件信封。
    """
    body = ConcurrentStableDict({"job_id": "42", "job_type": "sys.task.run", "service_key": "platform"})
    for key, value in payload.items():
        body.set(key, value)
    return EventEnvelope(event_type=event_type, payload=body, occurred_at=at, aggregate_key="job:42")


async def test_projection_follows_lifecycle(tmp_path: Path) -> None:
    """提交 → 开始 → 进度 → 完成：同一行持续更新，终态与错误摘要可见。"""
    engine, maker = await _session(tmp_path)
    try:
        async with maker() as session, session.begin():
            service = JobMonitorService(JobMonitorRepository(session))
            assert await service.apply(_event(JOB_SUBMITTED_EVENT, BASE, status="queued")) is True
            assert await service.apply(_event(JOB_STARTED_EVENT, BASE + timedelta(seconds=1), attempt=1)) is True
            assert (
                await service.apply(
                    _event(JOB_PROGRESS_EVENT, BASE + timedelta(seconds=2), progress_done=3, progress_total=10)
                )
                is True
            )
            assert (
                await service.apply(
                    _event(
                        JOB_COMPLETED_EVENT,
                        BASE + timedelta(seconds=3),
                        status="dead",
                        attempts=3,
                        error="boom",
                    )
                )
                is True
            )
        async with maker() as session:
            rows = (await session.execute(select(SysJobMonitor))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert int(row.job_id) == 42
        assert row.status == "dead"
        assert row.progress_done == 3 and row.progress_total == 10
        assert row.attempts == 3
        assert row.error == "boom"
        assert row.submitted_at is not None and row.started_at is not None and row.finished_at is not None
    finally:
        await engine.dispose()


async def test_stale_event_is_dropped(tmp_path: Path) -> None:
    """旧事件（last_event_at 更早）：丢弃，不覆盖终态。"""
    engine, maker = await _session(tmp_path)
    try:
        async with maker() as session, session.begin():
            service = JobMonitorService(JobMonitorRepository(session))
            await service.apply(
                _event(JOB_COMPLETED_EVENT, BASE + timedelta(seconds=10), status="succeeded", attempts=1)
            )
            applied = await service.apply(_event(JOB_STARTED_EVENT, BASE, attempt=1))
        assert applied is False
        async with maker() as session:
            row = (await session.execute(select(SysJobMonitor))).scalars().one()
        assert row.status == "succeeded"
    finally:
        await engine.dispose()


async def test_event_without_job_id_is_ignored(tmp_path: Path) -> None:
    """缺作业号的事件：不落投影。"""
    engine, maker = await _session(tmp_path)
    try:
        envelope = EventEnvelope(event_type=JOB_STARTED_EVENT, payload=ConcurrentStableDict(), occurred_at=BASE)
        async with maker() as session, session.begin():
            applied = await JobMonitorService(JobMonitorRepository(session)).apply(envelope)
        assert applied is False
    finally:
        await engine.dispose()
