"""作业生命周期事件护栏（Kiwi 2388）：四条契约字段 / 聚合键 / 版本 / 同事务写发件箱。"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.jobs.events import (
    JOB_COMPLETED_EVENT,
    JOB_EVENT_VERSION,
    JOB_PROGRESS_EVENT,
    JOB_STARTED_EVENT,
    JOB_SUBMITTED_EVENT,
    completed_envelope,
    enqueue_job_event,
    progress_envelope,
    started_envelope,
    submitted_envelope,
)
from bms_core.models.outbox import SysOutbox

pytestmark = pytest.mark.kiwi_id(2388)


def test_four_event_types() -> None:
    """四条事件类型与契约命名一致。"""
    assert (
        JOB_SUBMITTED_EVENT,
        JOB_STARTED_EVENT,
        JOB_PROGRESS_EVENT,
        JOB_COMPLETED_EVENT,
    ) == ("sys.job.submitted", "sys.job.started", "sys.job.progress", "sys.job.completed")


def test_submitted_envelope_fields() -> None:
    """提交事件：作业号 / 类型 / 服务 / 状态齐备，聚合键按作业。"""
    envelope = submitted_envelope(job_id=11, job_type="file.cleanup_orphans", service_key="file", status="queued")
    assert envelope.event_type == JOB_SUBMITTED_EVENT
    assert envelope.aggregate_key == "job:11"
    assert envelope.event_version == JOB_EVENT_VERSION
    assert envelope.payload == {
        "job_id": "11",
        "job_type": "file.cleanup_orphans",
        "service_key": "file",
        "status": "queued",
    }


def test_progress_total_optional() -> None:
    """进度事件：总量未知时负载不带 `progress_total`。"""
    envelope = progress_envelope(job_id=1, job_type="t", service_key="s", done=3, total=None)
    assert "progress_total" not in envelope.payload
    with_total = progress_envelope(job_id=1, job_type="t", service_key="s", done=3, total=10)
    assert with_total.payload["progress_total"] == 10


def test_completed_envelope_carries_terminal_state() -> None:
    """完成事件：终态 / 尝试次数 / 错误摘要。"""
    envelope = completed_envelope(job_id=2, job_type="t", service_key="s", status="dead", attempts=3, error="boom")
    assert envelope.payload["status"] == "dead"
    assert envelope.payload["attempts"] == 3
    assert envelope.payload["error"] == "boom"


async def test_enqueue_writes_outbox(session: AsyncSession) -> None:
    """事件与状态更新同事务写发件箱。"""
    envelope = started_envelope(job_id=3, job_type="t", service_key="s", attempt=1)
    async with session.begin():
        await enqueue_job_event(session, envelope)
    async with session.begin():
        rows = (await session.execute(select(SysOutbox))).scalars().all()
    assert len(rows) == 1
    assert rows[0].event_type == JOB_STARTED_EVENT
    assert rows[0].aggregate_key == "job:3"


_ = ConcurrentStableDict
