"""作业监控投影护栏（Kiwi 2386）：四条事件 upsert / 旧事件丢弃 / 终态覆盖。

单库叠加口径（04-6-2）：库用共享平台库、写入走 `rollback_session`（整体回滚不残留）；
作业主键按命名空间派生，断言只看本用例那一行。
"""

from datetime import datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope
from bms_core.jobs.events import (
    JOB_COMPLETED_EVENT,
    JOB_PROGRESS_EVENT,
    JOB_STARTED_EVENT,
    JOB_SUBMITTED_EVENT,
)
from bms_core.models.platform.job import SysJobMonitor
from bms_core.testing.namespace import Namespace
from bms_core.testing.schema import ensure_tables
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.job.repositories.job import JobMonitorRepository
from bms_platform.domains.job.services.monitor import JobMonitorService

pytestmark = pytest.mark.kiwi_id(2386)

BASE = datetime(2026, 11, 1, 3, 0, 0)


def _job_id(ns: Namespace) -> int:
    """按命名空间派生作业主键。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 作业主键。
    """
    return int(ns.prefix[2:], 16)


def _event(event_type: str, at: datetime, job_id: int, **payload: object) -> EventEnvelope:
    """构造作业事件。

    Args:
        event_type: 事件类型。
        at: 发生时刻。
        job_id: 作业主键（本用例专属）。
        **payload: 负载字段。

    Returns:
        EventEnvelope: 事件信封。
    """
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"job_id": str(job_id), "job_type": "sys.task.run", "service_key": "platform"}
    )
    for key, value in payload.items():
        body.set(key, value)
    return EventEnvelope(event_type=event_type, payload=body, occurred_at=at, aggregate_key=f"job:{job_id}")


async def test_projection_follows_lifecycle(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """提交 → 开始 → 进度 → 完成：同一行持续更新，终态与错误摘要可见。"""
    job_id = _job_id(ns)
    await ensure_tables(shared_platform_engine, [cast("Table", SysJobMonitor.__table__)])
    async with rollback_session(shared_platform_engine) as session:
        service = JobMonitorService(JobMonitorRepository(session))
        assert await service.apply(_event(JOB_SUBMITTED_EVENT, BASE, job_id, status="queued")) is True
        assert await service.apply(_event(JOB_STARTED_EVENT, BASE + timedelta(seconds=1), job_id, attempt=1)) is True
        assert (
            await service.apply(
                _event(JOB_PROGRESS_EVENT, BASE + timedelta(seconds=2), job_id, progress_done=3, progress_total=10)
            )
            is True
        )
        assert (
            await service.apply(
                _event(
                    JOB_COMPLETED_EVENT,
                    BASE + timedelta(seconds=3),
                    job_id,
                    status="dead",
                    attempts=3,
                    error="boom",
                )
            )
            is True
        )
        row = await JobMonitorRepository(session).get_by_job_id(job_id)
        assert row is not None
        assert int(row.job_id) == job_id
        assert row.status == "dead"
        assert row.progress_done == 3 and row.progress_total == 10
        assert row.attempts == 3
        assert row.error == "boom"
        assert row.submitted_at is not None and row.started_at is not None and row.finished_at is not None


async def test_stale_event_is_dropped(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """旧事件（last_event_at 更早）：丢弃，不覆盖终态。"""
    job_id = _job_id(ns)
    await ensure_tables(shared_platform_engine, [cast("Table", SysJobMonitor.__table__)])
    async with rollback_session(shared_platform_engine) as session:
        service = JobMonitorService(JobMonitorRepository(session))
        await service.apply(
            _event(JOB_COMPLETED_EVENT, BASE + timedelta(seconds=10), job_id, status="succeeded", attempts=1)
        )
        applied = await service.apply(_event(JOB_STARTED_EVENT, BASE, job_id, attempt=1))
        assert applied is False
        row = await JobMonitorRepository(session).get_by_job_id(job_id)
        assert row is not None and row.status == "succeeded"


async def test_event_without_job_id_is_ignored(shared_platform_engine: AsyncEngine) -> None:
    """缺作业号的事件：不落投影。"""
    await ensure_tables(shared_platform_engine, [cast("Table", SysJobMonitor.__table__)])
    async with rollback_session(shared_platform_engine) as session:
        envelope = EventEnvelope(event_type=JOB_STARTED_EVENT, payload=ConcurrentStableDict(), occurred_at=BASE)
        applied = await JobMonitorService(JobMonitorRepository(session)).apply(envelope)
        assert applied is False
