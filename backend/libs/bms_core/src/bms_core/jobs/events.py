"""作业生命周期事件：四条契约的构造与同事务发件箱写入。

- `sys.job.submitted` / `sys.job.started` / `sys.job.progress` / `sys.job.completed`（版本 `1.0.0`）；
- 事件与作业状态更新**同一会话**写入 `sys_outbox`（生产一致性由既有投递器保证）；
- `aggregate_key = job:{job_id}` 保证同一作业的事件按序投递；
- `completed` 携带终态与尝试次数，同时作为通知中心后续消费的完成事件。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.store import SqlOutboxStore

__all__ = [
    "JOB_COMPLETED_EVENT",
    "JOB_EVENT_VERSION",
    "JOB_PROGRESS_EVENT",
    "JOB_STARTED_EVENT",
    "JOB_SUBMITTED_EVENT",
    "completed_envelope",
    "enqueue_job_event",
    "progress_envelope",
    "started_envelope",
    "submitted_envelope",
]

JOB_EVENT_VERSION = "1.0.0"
"""作业事件契约版本。"""

JOB_SUBMITTED_EVENT = "sys.job.submitted"
"""作业提交成功（同事务发件箱）。"""

JOB_STARTED_EVENT = "sys.job.started"
"""作业抢占成功、开始执行。"""

JOB_PROGRESS_EVENT = "sys.job.progress"
"""作业进度更新（节流）。"""

JOB_COMPLETED_EVENT = "sys.job.completed"
"""作业进入终态（succeeded / failed / canceled / dead）。"""


def _envelope(event_type: str, job_id: int, payload: ConcurrentStableDict[str, object]) -> EventEnvelope:
    """构造作业事件信封（同作业聚合键有序）。

    Args:
        event_type: 事件类型。
        job_id: 作业主键。
        payload: 事件负载。

    Returns:
        EventEnvelope: 事件信封。
    """
    return EventEnvelope(
        event_type=event_type,
        payload=payload,
        aggregate_key=f"job:{job_id}",
        event_version=JOB_EVENT_VERSION,
    )


def submitted_envelope(*, job_id: int, job_type: str, service_key: str, status: str) -> EventEnvelope:
    """构造 `sys.job.submitted` 事件。

    Args:
        job_id: 作业主键。
        job_type: 作业类型。
        service_key: 提供方服务键。
        status: 提交后的状态。

    Returns:
        EventEnvelope: 事件信封。
    """
    return _envelope(
        JOB_SUBMITTED_EVENT,
        job_id,
        ConcurrentStableDict(
            {"job_id": str(job_id), "job_type": job_type, "service_key": service_key, "status": status}
        ),
    )


def started_envelope(*, job_id: int, job_type: str, service_key: str, attempt: int) -> EventEnvelope:
    """构造 `sys.job.started` 事件。

    Args:
        job_id: 作业主键。
        job_type: 作业类型。
        service_key: 提供方服务键。
        attempt: 本次是第几次执行。

    Returns:
        EventEnvelope: 事件信封。
    """
    return _envelope(
        JOB_STARTED_EVENT,
        job_id,
        ConcurrentStableDict(
            {"job_id": str(job_id), "job_type": job_type, "service_key": service_key, "attempt": int(attempt)}
        ),
    )


def progress_envelope(*, job_id: int, job_type: str, service_key: str, done: int, total: int | None) -> EventEnvelope:
    """构造 `sys.job.progress` 事件。

    Args:
        job_id: 作业主键。
        job_type: 作业类型。
        service_key: 提供方服务键。
        done: 已完成量。
        total: 总量（None = 不确定进度，不写入负载）。

    Returns:
        EventEnvelope: 事件信封。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "job_id": str(job_id),
            "job_type": job_type,
            "service_key": service_key,
            "progress_done": int(done),
        }
    )
    if total is not None:
        payload.set("progress_total", int(total))
    return _envelope(JOB_PROGRESS_EVENT, job_id, payload)


def completed_envelope(
    *,
    job_id: int,
    job_type: str,
    service_key: str,
    status: str,
    attempts: int,
    error: str | None = None,
) -> EventEnvelope:
    """构造 `sys.job.completed` 事件。

    Args:
        job_id: 作业主键。
        job_type: 作业类型。
        service_key: 提供方服务键。
        status: 终态。
        attempts: 已执行次数。
        error: 错误摘要（成功 / 取消可为空）。

    Returns:
        EventEnvelope: 事件信封。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "job_id": str(job_id),
            "job_type": job_type,
            "service_key": service_key,
            "status": status,
            "attempts": int(attempts),
        }
    )
    if error:
        payload.set("error", error)
    return _envelope(JOB_COMPLETED_EVENT, job_id, payload)


async def enqueue_job_event(
    session: DbSession, envelope: EventEnvelope, *, outbox: BaseOutboxStore | None = None
) -> str:
    """把作业事件写入同事务发件箱。

    Args:
        session: 作业状态更新所在会话。
        envelope: 事件信封。
        outbox: 发件箱存储（缺省 SQL 实现）。

    Returns:
        str: 事件 ID。
    """
    store = outbox if outbox is not None else SqlOutboxStore()
    return await store.enqueue(session, envelope)
