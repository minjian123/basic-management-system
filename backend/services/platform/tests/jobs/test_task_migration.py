"""任务执行作业迁移护栏（Kiwi 2383）：TaskJobHandler 回写 `sys_task_log` 并发完成事件。

单库叠加口径（04-6-2）：库用共享平台库、写入走 `rollback_session`（整体回滚不残留）；
任务主键按命名空间派生，发件箱断言按 `aggregate_key`（`task:<task_id>`）限定到本用例的事件。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.session import DbSession
from bms_core.jobs.base import JobContext
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.task import TASK_RUN_RUNNING, SysTaskLog
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.task.jobs import TaskJobHandler

pytestmark = pytest.mark.kiwi_id(2383)

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    (cast("Table", SysTaskLog.__table__), cast("Table", SysOutbox.__table__))
)
"""本文件涉及的表（共享平台库幂等补齐）。"""


@pytest.fixture
async def session(shared_platform_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """共享平台库上的回滚会话（任务日志 / 发件箱两表幂等补齐）。"""
    async with shared_platform_engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(_TABLES)))
    async with rollback_session(shared_platform_engine) as opened:
        yield opened


async def _context(
    session: AsyncSession, *, task_id: int, job_id: int, code: str, handler: str
) -> tuple[JobContext, int]:
    """建一条运行中的任务日志并构造执行上下文（会话复用回滚会话）。

    Args:
        session: 回滚会话。
        task_id: 任务主键（本用例专属）。
        job_id: 作业主键。
        code: 任务编码。
        handler: 执行体路径。

    Returns:
        tuple[JobContext, int]: （执行上下文, 任务日志主键）。
    """
    log = SysTaskLog(
        task_id=task_id, run_id=f"r{task_id}", trigger_source="schedule", status=TASK_RUN_RUNNING, retry_count=0
    )
    session.add(log)
    await session.flush()
    log_id = int(log.id)

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        yield session

    ctx = JobContext(
        job_id=job_id,
        job_type="sys.task.run",
        service_key="platform",
        db_key="platform",
        payload=ConcurrentStableDict(
            {
                "task_id": task_id,
                "log_id": log_id,
                "run_id": f"r{task_id}",
                "code": code,
                "handler": handler,
                "args_json": None,
            }
        ),
        attempt=1,
        max_attempts=3,
        open_session=_open,
    )
    return ctx, log_id


async def _task_log(session: AsyncSession, log_id: int) -> SysTaskLog:
    """按主键取任务日志行。

    Args:
        session: 回滚会话。
        log_id: 任务日志主键。

    Returns:
        SysTaskLog: 日志行。
    """
    return (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalars().one()


async def test_handler_writes_task_log_and_event(session: AsyncSession, ns: Namespace) -> None:
    """内置占位任务（skipped）：日志收敛 `skipped`，并写 `sys.task.completed`。"""
    task_id = int(ns.prefix[2:], 16)
    ctx, log_id = await _context(
        session,
        task_id=task_id,
        job_id=task_id * 10,
        code="archive_audit_logs",
        handler="bms_core.tasks.builtin:run_archive_audit_logs",
    )
    result = await TaskJobHandler().run(ctx)
    assert result.status == "succeeded"
    row = await _task_log(session, log_id)
    events = (
        (await session.execute(select(SysOutbox).where(SysOutbox.aggregate_key == f"task:{task_id}"))).scalars().all()
    )
    assert row.status == "skipped"
    assert row.finished_at is not None
    assert row.cost_time is not None
    assert [item.event_type for item in events] == ["sys.task.completed"]


async def test_handler_rejects_handler_outside_whitelist(session: AsyncSession, ns: Namespace) -> None:
    """执行体不在白名单：返回不可重试失败并回写 failed（不执行任意代码）。"""
    task_id = int(ns.prefix[2:], 16) + 1
    ctx, log_id = await _context(session, task_id=task_id, job_id=task_id * 10, code="evil", handler="os.system:system")
    result = await TaskJobHandler().run(ctx)
    assert result.status == "failed"
    assert result.retryable is False
    row = await _task_log(session, log_id)
    assert row.status == "failed"
    assert row.error_msg


_ = DbSession
