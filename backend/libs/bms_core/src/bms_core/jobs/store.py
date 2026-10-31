"""`sys_job` / `sys_job_error` 读写：提交、条件抢占、续租、进度、终态、回收、清理。

**唯一写作业表入口**：业务代码不得直接拼 SQL 或另建作业表；提交 / 抢占 / 终态一律经本模块。

**抢占为什么用条件 UPDATE**：多 worker 与租约回收同时发生时，`UPDATE ... WHERE status='queued'`
是同一行上的原子 CAS——第二个 worker 因 `rowcount = 0` 放弃，重复执行在数据库层被挡住。
不依赖 `SKIP LOCKED`，SQLite / MySQL / PostgreSQL / 达梦同一口径。

本模块**不开事务**：事务边界归调用方（`JobRunner` / `JobWorker` / API 服务）。
**幂等并发穿透**：`submit_job` 只做「先查 + 插入」；唯一约束冲突由 `JobRunner` 在独立事务中回滚后
回读既有作业（失败事务不可继续查询，故不在本模块内吞掉 `IntegrityError`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.jobs.spec import JobSnapshot, JobSubmission, dump_payload, now_utc, parse_job_payload
from bms_core.models.job import (
    DEFAULT_PAYLOAD_VERSION,
    JOB_STATUS_CANCELED,
    JOB_STATUS_DEAD,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_TERMINAL_STATUSES,
    SysJob,
    SysJobError,
)

__all__ = [
    "CANCEL_MISSING",
    "CANCEL_TERMINAL",
    "CANCEL_UPDATED",
    "RETRY_MISSING",
    "RETRY_TERMINAL",
    "RETRY_UPDATED",
    "JobClaim",
    "ReclaimResult",
    "RetryResult",
    "add_job_error",
    "claim_candidates",
    "claim_job",
    "cleanup_finished_jobs",
    "find_by_idempotency",
    "finish_job",
    "get_job",
    "heartbeat",
    "list_job_errors",
    "mark_dead",
    "reclaim_expired",
    "request_cancel",
    "requeue_job",
    "retry_job",
    "snapshot_of",
    "submit_job",
    "update_progress",
]

CANCEL_UPDATED = "canceled"
"""取消结果：队列中作业已直接取消。"""

CANCEL_TERMINAL = "terminal"
"""取消结果：作业已处终态（不可取消）。"""

CANCEL_MISSING = "missing"
"""取消结果：作业不存在。"""

RETRY_UPDATED = "retried"
"""重试结果：已重置回队。"""

RETRY_TERMINAL = "terminal"
"""重试结果：状态不可重试。"""

RETRY_MISSING = "missing"
"""重试结果：作业不存在。"""


@dataclass(frozen=True)
class JobClaim(BaseValueObject):
    """抢占候选（只带定位与尝试信息）。"""

    job_id: int
    """作业主键。"""

    attempts: int
    """已执行次数。"""

    max_attempts: int
    """最大执行次数。"""

    priority: int
    """优先级。"""


@dataclass(frozen=True)
class ReclaimResult(BaseValueObject):
    """租约回收结果。"""

    requeued: int = 0
    """回队条数。"""

    dead: int = 0
    """转死信条数。"""


@dataclass(frozen=True)
class RetryResult(BaseValueObject):
    """人工重试结果。"""

    status: str
    """`retried` / `terminal` / `missing`。"""


def _values(**changes: object) -> dict[str, object]:
    """构造条件更新值（自动递增乐观锁版本）。

    Args:
        **changes: 业务列变更。

    Returns:
        dict[str, object]: 更新值。
    """
    payload = dict(changes)
    payload["version"] = SysJob.version + 1
    return payload


async def find_by_idempotency(
    session: DbSession, *, job_type: str, idempotency_key: str
) -> SysJob | None:
    """按幂等键查既有作业。

    Args:
        session: 作业所在库会话。
        job_type: 作业类型。
        idempotency_key: 幂等键。

    Returns:
        SysJob | None: 命中返回既有作业。
    """
    stmt = select(SysJob).where(
        SysJob.job_type == job_type,
        SysJob.idempotency_key == idempotency_key,
        SysJob.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalars().first()


async def get_job(session: DbSession, job_id: int) -> SysJob | None:
    """按主键取作业。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。

    Returns:
        SysJob | None: 作业记录（含已软删）。
    """
    return (await session.execute(select(SysJob).where(SysJob.id == job_id))).scalars().first()


async def submit_job(
    session: DbSession,
    *,
    submission: JobSubmission,
    service_key: str,
    domain_key: str,
    max_attempts: int,
    tenant_id: int | None = None,
    now: datetime | None = None,
) -> tuple[SysJob, bool]:
    """提交作业（同事务写记录；幂等键命中返回既有作业）。

    Args:
        session: 作业所在库会话。
        submission: 提交规格。
        service_key: 提供方服务键。
        domain_key: 提供方业务域。
        max_attempts: 最大执行次数（已按声明 / 默认解析）。
        tenant_id: 租户主键（平台链为 None）。
        now: 当前时刻（测试注入）。

    Returns:
        tuple[SysJob, bool]: （作业记录, 是否新建）。

    Raises:
        IntegrityError: 幂等键并发穿透且回读仍缺失（由调用方转业务错误）。
    """
    moment = now if now is not None else now_utc()
    if submission.idempotency_key:
        existing = await find_by_idempotency(
            session, job_type=submission.job_type, idempotency_key=submission.idempotency_key
        )
        if existing is not None:
            return existing, False
    record = SysJob(
        job_type=submission.job_type,
        service_key=service_key,
        domain_key=domain_key,
        tenant_id=tenant_id,
        status=JOB_STATUS_QUEUED,
        priority=submission.priority,
        payload=dump_payload(submission.payload),
        payload_version=submission.payload_version or DEFAULT_PAYLOAD_VERSION,
        progress_done=0,
        progress_total=None,
        attempts=0,
        max_attempts=max_attempts,
        cancel_requested=False,
        idempotency_key=submission.idempotency_key,
    )
    # `moment` 仅用于语义占位：审计时间由 ORM 事件统一填充（避免双源）。
    _ = moment
    session.add(record)
    await session.flush()
    return record, True


async def claim_candidates(
    session: DbSession, *, now: datetime, limit: int, job_types: ConcurrentStableList[str] | None = None
) -> ConcurrentStableList[JobClaim]:
    """取可抢占候选（同租户内 priority 大者先、插入序在前）。

    Args:
        session: 作业所在库会话。
        now: 当前时刻。
        limit: 单次上限。
        job_types: 只取指定作业类型（None 取全部）。

    Returns:
        ConcurrentStableList[JobClaim]: 候选清单。
    """
    stmt = (
        select(SysJob.id, SysJob.attempts, SysJob.max_attempts, SysJob.priority)
        .where(
            SysJob.status == JOB_STATUS_QUEUED,
            SysJob.deleted_at.is_(None),
            or_(SysJob.next_run_at.is_(None), SysJob.next_run_at <= now),
        )
        .order_by(SysJob.priority.desc(), SysJob.id.asc())
        .limit(limit)
    )
    if job_types:
        stmt = stmt.where(SysJob.job_type.in_(list(job_types)))
    rows = (await session.execute(stmt)).all()
    return ConcurrentStableList(
        JobClaim(job_id=int(row[0]), attempts=int(row[1]), max_attempts=int(row[2]), priority=int(row[3]))
        for row in rows
    )


async def claim_job(
    session: DbSession, *, job_id: int, worker_id: str, lease_until: datetime, now: datetime
) -> bool:
    """条件 UPDATE 抢占一条作业（`rowcount=1` 才算抢到）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        worker_id: 执行者实例标识。
        lease_until: 租约到期时刻。
        now: 当前时刻。

    Returns:
        bool: 抢到 True；被其他 worker 抢走 / 状态已变 False。
    """
    stmt = (
        update(SysJob)
        .where(
            SysJob.id == job_id,
            SysJob.status == JOB_STATUS_QUEUED,
            SysJob.deleted_at.is_(None),
            or_(SysJob.next_run_at.is_(None), SysJob.next_run_at <= now),
        )
        .values(
            **_values(
                status=JOB_STATUS_RUNNING,
                lease_owner=worker_id,
                lease_until=lease_until,
                attempts=SysJob.attempts + 1,
                started_at=func.coalesce(SysJob.started_at, now),
                last_heartbeat_at=now,
                updated_at=now,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def heartbeat(
    session: DbSession, *, job_id: int, worker_id: str, lease_until: datetime, now: datetime
) -> bool:
    """续租（执行期间心跳；只续自己持有的租约）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        worker_id: 执行者实例标识。
        lease_until: 新的租约到期时刻。
        now: 当前时刻。

    Returns:
        bool: 续租成功 True；租约已被回收 / 转手 False。
    """
    stmt = (
        update(SysJob)
        .where(
            SysJob.id == job_id,
            SysJob.status == JOB_STATUS_RUNNING,
            SysJob.lease_owner == worker_id,
            SysJob.deleted_at.is_(None),
        )
        .values(**_values(lease_until=lease_until, last_heartbeat_at=now, updated_at=now))
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def update_progress(
    session: DbSession, *, job_id: int, done: int, total: int | None, now: datetime
) -> bool:
    """更新进度（运行中作业；同时刷新心跳）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        done: 已完成量。
        total: 总量（None = 不确定进度）。
        now: 当前时刻。

    Returns:
        bool: 更新成功 True；作业已不在运行 False。
    """
    stmt = (
        update(SysJob)
        .where(SysJob.id == job_id, SysJob.status == JOB_STATUS_RUNNING, SysJob.deleted_at.is_(None))
        .values(
            **_values(
                progress_done=int(done),
                progress_total=None if total is None else int(total),
                last_heartbeat_at=now,
                updated_at=now,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def request_cancel(session: DbSession, *, job_id: int, now: datetime, reason: str | None = None) -> str:
    """请求取消（队列中直接取消；运行中置取消标记由 handler 协作收尾）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        now: 当前时刻。
        reason: 取消原因（写备注）。

    Returns:
        str: `canceled` / `requested` / `terminal` / `missing`。
    """
    record = await get_job(session, job_id)
    if record is None or record.deleted_at is not None:
        return CANCEL_MISSING
    if record.status in JOB_TERMINAL_STATUSES:
        return CANCEL_TERMINAL
    if record.status == JOB_STATUS_QUEUED:
        stmt = (
            update(SysJob)
            .where(SysJob.id == job_id, SysJob.status == JOB_STATUS_QUEUED, SysJob.deleted_at.is_(None))
            .values(
                **_values(
                    status=JOB_STATUS_CANCELED,
                    cancel_requested=True,
                    finished_at=now,
                    remark=reason,
                    updated_at=now,
                )
            )
        )
        result = cast("CursorResult[Any]", await session.execute(stmt))
        return CANCEL_UPDATED if result.rowcount == 1 else CANCEL_TERMINAL
    stmt = (
        update(SysJob)
        .where(SysJob.id == job_id, SysJob.status == JOB_STATUS_RUNNING, SysJob.deleted_at.is_(None))
        .values(**_values(cancel_requested=True, remark=reason, updated_at=now))
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return CANCEL_UPDATED if result.rowcount == 1 else CANCEL_TERMINAL


async def finish_job(
    session: DbSession,
    *,
    job_id: int,
    status: str,
    finished_at: datetime,
    result_text: str | None = None,
    error_text: str | None = None,
    remark: str | None = None,
) -> bool:
    """运行中作业收敛到终态（只更新仍处于 running 的记录）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        status: 终态（`succeeded` / `failed` / `canceled` / `dead`）。
        finished_at: 结束时刻。
        result_text: 结果 JSON（已截断）。
        error_text: 错误摘要（已截断）。
        remark: 备注。

    Returns:
        bool: 更新成功 True；已被回收 / 转手 False。
    """
    if status not in JOB_TERMINAL_STATUSES:
        raise ValueError(f"非终态不可落终态：{status}")
    stmt = (
        update(SysJob)
        .where(SysJob.id == job_id, SysJob.status == JOB_STATUS_RUNNING, SysJob.deleted_at.is_(None))
        .values(
            **_values(
                status=status,
                finished_at=finished_at,
                result=result_text,
                error=error_text,
                remark=remark,
                lease_owner=None,
                lease_until=None,
                last_heartbeat_at=finished_at,
                updated_at=finished_at,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def requeue_job(
    session: DbSession, *, job_id: int, next_run_at: datetime, error_text: str | None, now: datetime
) -> bool:
    """可重试失败：回队并设置退避时刻（attempts 保留）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        next_run_at: 下次可执行时刻。
        error_text: 错误摘要。
        now: 当前时刻。

    Returns:
        bool: 回队成功 True。
    """
    stmt = (
        update(SysJob)
        .where(SysJob.id == job_id, SysJob.status == JOB_STATUS_RUNNING, SysJob.deleted_at.is_(None))
        .values(
            **_values(
                status=JOB_STATUS_QUEUED,
                next_run_at=next_run_at,
                error=error_text,
                lease_owner=None,
                lease_until=None,
                updated_at=now,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def mark_dead(session: DbSession, *, job_id: int, error_text: str, now: datetime) -> bool:
    """置死信（重试耗尽 / 不可重试 / 租约回收超限）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        error_text: 失败原因（已截断）。
        now: 当前时刻。

    Returns:
        bool: 置死信成功 True。
    """
    stmt = (
        update(SysJob)
        .where(
            SysJob.id == job_id,
            SysJob.status.in_((JOB_STATUS_RUNNING, JOB_STATUS_QUEUED)),
            SysJob.deleted_at.is_(None),
        )
        .values(
            **_values(
                status=JOB_STATUS_DEAD,
                error=error_text,
                finished_at=now,
                lease_owner=None,
                lease_until=None,
                updated_at=now,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def reclaim_expired(session: DbSession, *, now: datetime, limit: int = 50) -> ReclaimResult:
    """回收租约过期的运行中作业（未达上限回队，达上限转死信）。

    Args:
        session: 作业所在库会话。
        now: 当前时刻。
        limit: 单次上限。

    Returns:
        ReclaimResult: 回队 / 死信件数。
    """
    stmt = (
        select(SysJob.id, SysJob.attempts, SysJob.max_attempts)
        .where(
            SysJob.status == JOB_STATUS_RUNNING,
            SysJob.deleted_at.is_(None),
            SysJob.lease_until.is_not(None),
            SysJob.lease_until < now,
        )
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    requeued = 0
    dead = 0
    for row in rows:
        job_id = int(row[0])
        attempts = int(row[1])
        max_attempts = int(row[2])
        if attempts >= max_attempts:
            if await mark_dead(session, job_id=job_id, error_text="租约过期且重试耗尽（执行者失联）", now=now):
                dead += 1
        elif await requeue_job(
            session, job_id=job_id, next_run_at=now, error_text="租约过期，重新排队（执行者失联）", now=now
        ):
            requeued += 1
    return ReclaimResult(requeued=requeued, dead=dead)


async def retry_job(session: DbSession, *, job_id: int, now: datetime) -> RetryResult:
    """人工重试死信 / 失败作业（重置尝试次数并回队）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        now: 当前时刻。

    Returns:
        RetryResult: 重试结果状态。
    """
    record = await get_job(session, job_id)
    if record is None or record.deleted_at is not None:
        return RetryResult(status=RETRY_MISSING)
    if record.status not in (JOB_STATUS_DEAD, JOB_STATUS_FAILED):
        return RetryResult(status=RETRY_TERMINAL)
    stmt = (
        update(SysJob)
        .where(
            SysJob.id == job_id,
            SysJob.status.in_((JOB_STATUS_DEAD, JOB_STATUS_FAILED)),
            SysJob.deleted_at.is_(None),
        )
        .values(
            **_values(
                status=JOB_STATUS_QUEUED,
                attempts=0,
                next_run_at=None,
                cancel_requested=False,
                error=None,
                finished_at=None,
                lease_owner=None,
                lease_until=None,
                updated_at=now,
            )
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return RetryResult(status=RETRY_UPDATED if result.rowcount == 1 else RETRY_TERMINAL)


async def add_job_error(
    session: DbSession,
    *,
    job_id: int,
    message: str,
    row_no: int | None = None,
    column_key: str | None = None,
    item_ref: str | None = None,
) -> None:
    """写一条行级错误明细。

    Args:
        session: 作业所在库会话。
        job_id: 所属作业主键。
        message: 错误原因（截断 512）。
        row_no: 业务行号。
        column_key: 出错列 / 字段键。
        item_ref: 业务条目标识。
    """
    session.add(
        SysJobError(
            job_id=job_id,
            row_no=row_no,
            column_key=column_key,
            item_ref=item_ref,
            message=message[:512],
        )
    )
    await session.flush()


async def list_job_errors(session: DbSession, *, job_id: int, limit: int = 100) -> ConcurrentStableList[SysJobError]:
    """取作业行级错误明细（插入序）。

    Args:
        session: 作业所在库会话。
        job_id: 作业主键。
        limit: 上限。

    Returns:
        ConcurrentStableList[SysJobError]: 错误明细。
    """
    stmt = (
        select(SysJobError)
        .where(SysJobError.job_id == job_id, SysJobError.deleted_at.is_(None))
        .order_by(SysJobError.id.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return ConcurrentStableList(rows)


async def cleanup_finished_jobs(session: DbSession, *, cutoff: datetime) -> int:
    """清理超过保留期的终态作业与行级错误（硬删；运行中 / 待执行不删）。

    Args:
        session: 作业所在库会话。
        cutoff: 终态时间阈值（`finished_at < cutoff` 删除）。

    Returns:
        int: 删除的作业条数。
    """
    expired = select(SysJob.id).where(
        SysJob.status.in_(JOB_TERMINAL_STATUSES),
        SysJob.finished_at.is_not(None),
        SysJob.finished_at < cutoff,
    )
    await session.execute(delete(SysJobError).where(SysJobError.job_id.in_(expired)))
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(SysJob).where(
                SysJob.status.in_(JOB_TERMINAL_STATUSES),
                SysJob.finished_at.is_not(None),
                SysJob.finished_at < cutoff,
            )
        ),
    )
    return int(result.rowcount)


def snapshot_of(record: SysJob) -> JobSnapshot:
    """把 ORM 行转只读快照（跨会话安全）。

    Args:
        record: 作业记录。

    Returns:
        JobSnapshot: 只读快照。
    """
    return JobSnapshot(
        id=int(record.id),
        job_type=record.job_type,
        service_key=record.service_key,
        domain_key=record.domain_key,
        status=record.status,
        payload=parse_job_payload(record.payload),
        payload_version=record.payload_version,
        priority=int(record.priority),
        tenant_id=record.tenant_id,
        progress_done=int(record.progress_done),
        progress_total=record.progress_total,
        attempts=int(record.attempts),
        max_attempts=int(record.max_attempts),
        cancel_requested=bool(record.cancel_requested),
        error=record.error,
        idempotency_key=record.idempotency_key,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )
