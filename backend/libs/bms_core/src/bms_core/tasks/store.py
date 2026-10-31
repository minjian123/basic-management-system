"""`sys_task` / `sys_task_log` 读写：到期候选、**条件 UPDATE 抢占**、记录写入、超时回收。

**抢占为什么用条件 UPDATE**（《详细设计 · 任务调度》§4.3 关键点 1）：
Redis 锁在 TTL 到期 / 网络分区 / 进程被强杀时会出现「两个 beat 同时认为自己持有锁」的窗口；
`UPDATE ... WHERE next_run_at <= now` 是**同一行上的原子 CAS**——第二个 beat 因 `next_run_at`
已被推进而 `rowcount = 0`，重复派发在数据库层就被挡住。锁只用来省掉无谓扫描。

本模块**不开事务**：事务边界归调用方（调度器按租户一轮一个事务），与 `SqlOutboxStore` 同口径。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select, update

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.models.platform.task import (
    TASK_RUN_FAILED,
    TASK_RUN_RUNNING,
    TASK_STATUS_DISABLED,
    TASK_STATUS_ENABLED,
    SysTask,
    SysTaskLog,
)

__all__ = [
    "TaskClaim",
    "claim_task",
    "create_run_record",
    "disable_task",
    "list_due_tasks",
    "reclaim_timeout_runs",
]

TIMEOUT_ERROR = "执行超时未完成（worker 失联）"
"""超时回收写入的错误摘要（与看板检索口径一致）。"""


@dataclass(frozen=True)
class TaskClaim(BaseValueObject):
    """到期候选（选取结果；抢占成功后才会落执行记录）。"""

    task_id: int
    """任务定义主键。"""

    code: str
    """任务代码（handler 注册键）。"""

    handler: str
    """执行体点分路径。"""

    cron: str
    """调度表达式（已确认非空）。"""

    args_json: str | None = None
    """参数原文。"""


async def list_due_tasks(session: DbSession, *, now: datetime, limit: int) -> ConcurrentStableList[TaskClaim]:
    """取到期候选（启用、有 cron、未到期推进或已到期）。

    Args:
        session: 租户库会话。
        now: 当前时刻（UTC naive）。
        limit: 单次上限。

    Returns:
        ConcurrentStableList[TaskClaim]: 候选清单（按到期时间升序）。
    """
    stmt = (
        select(SysTask.id, SysTask.code, SysTask.handler, SysTask.cron, SysTask.args)
        .where(
            SysTask.status == TASK_STATUS_ENABLED,
            SysTask.deleted_at.is_(None),
            SysTask.cron.is_not(None),
            or_(SysTask.next_run_at.is_(None), SysTask.next_run_at <= now),
        )
        .order_by(SysTask.next_run_at.is_(None).desc(), SysTask.next_run_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    claims: ConcurrentStableList[TaskClaim] = ConcurrentStableList()
    for row in rows:
        claims.append(
            TaskClaim(
                task_id=int(row[0]),
                code=str(row[1]),
                handler=str(row[2]),
                cron=str(row[3]),
                args_json=str(row[4]) if row[4] is not None else None,
            )
        )
    return claims


async def claim_task(
    session: DbSession,
    *,
    task_id: int,
    next_run_at: datetime | None,
    now: datetime,
) -> bool:
    """条件 UPDATE 抢占一条任务（同时推进 `next_run_at` 与 `last_run_at`）。

    Args:
        session: 租户库会话。
        task_id: 任务主键。
        next_run_at: 抢占成功后写入的下次到期时间（None 表示不再排期）。
        now: 当前时刻（UTC naive）。

    Returns:
        bool: 抢到 True；被其他实例抢先 / 任务已停用或删除 False。
    """
    stmt = (
        update(SysTask)
        .where(
            SysTask.id == task_id,
            SysTask.status == TASK_STATUS_ENABLED,
            SysTask.deleted_at.is_(None),
            SysTask.cron.is_not(None),
            or_(SysTask.next_run_at.is_(None), SysTask.next_run_at <= now),
        )
        .values(
            next_run_at=next_run_at,
            last_run_at=now,
            updated_at=now,
            version=SysTask.version + 1,
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1


async def create_run_record(
    session: DbSession,
    *,
    task_id: int,
    run_id: str,
    trigger_source: str,
    started_at: datetime,
) -> int:
    """写一条 `running` 执行记录（先落记录再入队）。

    Args:
        session: 租户库会话。
        task_id: 任务主键。
        run_id: 本次执行标识。
        trigger_source: 触发来源。
        started_at: 开始时刻（UTC naive）。

    Returns:
        int: 执行记录主键。
    """
    record = SysTaskLog(
        task_id=task_id,
        run_id=run_id,
        trigger_source=trigger_source,
        status=TASK_RUN_RUNNING,
        retry_count=0,
        started_at=started_at,
    )
    session.add(record)
    await session.flush()
    return int(record.id)


async def reclaim_timeout_runs(session: DbSession, *, cutoff: datetime, finished_at: datetime) -> int:
    """把超时仍处于 `running` 的记录回收为 `failed`（worker 失联兜底）。

    Args:
        session: 租户库会话。
        cutoff: 超时阈值（早于该时刻开始的 running 记录被回收）。
        finished_at: 回收时间（写 `finished_at`）。

    Returns:
        int: 回收条数。
    """
    stmt = (
        update(SysTaskLog)
        .where(
            SysTaskLog.status == TASK_RUN_RUNNING,
            SysTaskLog.deleted_at.is_(None),
            SysTaskLog.started_at.is_not(None),
            SysTaskLog.started_at < cutoff,
        )
        .values(
            status=TASK_RUN_FAILED,
            error_msg=TIMEOUT_ERROR,
            finished_at=finished_at,
            updated_at=finished_at,
            version=SysTaskLog.version + 1,
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return int(result.rowcount)


async def disable_task(session: DbSession, *, task_id: int, now: datetime) -> bool:
    """停用一条任务（cron 无法计算时的安全动作：不再派发、不再每轮重试）。

    Args:
        session: 租户库会话。
        task_id: 任务主键。
        now: 当前时刻（UTC naive）。

    Returns:
        bool: 停用成功 True。
    """
    stmt = (
        update(SysTask)
        .where(
            SysTask.id == task_id,
            SysTask.status == TASK_STATUS_ENABLED,
            SysTask.deleted_at.is_(None),
        )
        .values(
            status=TASK_STATUS_DISABLED,
            enabled=False,
            next_run_at=None,
            updated_at=now,
            version=SysTask.version + 1,
        )
    )
    result = cast("CursorResult[Any]", await session.execute(stmt))
    return result.rowcount == 1
