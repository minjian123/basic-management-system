"""任务执行作业迁移护栏（Kiwi 2383）：TaskJobHandler 回写 `sys_task_log` 并发完成事件。"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession
from bms_core.jobs.base import JobContext
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.task import TASK_RUN_RUNNING, SysTaskLog
from bms_platform.domains.task.jobs import TaskJobHandler

pytestmark = pytest.mark.kiwi_id(2383)


async def test_handler_writes_task_log_and_event(tmp_path: Path) -> None:
    """内置占位任务（skipped）：日志收敛 `skipped`，并写 `sys.task.completed`。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'task.log.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[SysTaskLog.__table__, SysOutbox.__table__])
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        log = SysTaskLog(task_id=1, run_id="r", trigger_source="schedule", status=TASK_RUN_RUNNING, retry_count=0)
        session.add(log)
        await session.flush()
        log_id = int(log.id)

    @asynccontextmanager
    async def _open() -> Any:
        async with maker() as session:
            yield session

    ctx = JobContext(
        job_id=100,
        job_type="sys.task.run",
        service_key="platform",
        db_key="platform",
        payload=ConcurrentStableDict(
            {
                "task_id": 1,
                "log_id": log_id,
                "run_id": "r",
                "code": "archive_audit_logs",
                "handler": "bms_core.tasks.builtin:run_archive_audit_logs",
                "args_json": None,
            }
        ),
        attempt=1,
        max_attempts=3,
        open_session=_open,
    )
    try:
        result = await TaskJobHandler().run(ctx)
        assert result.status == "succeeded"
        async with maker() as session:
            row = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalars().one()
            events = (await session.execute(select(SysOutbox))).scalars().all()
        assert row.status == "skipped"
        assert row.finished_at is not None
        assert row.cost_time is not None
        assert [item.event_type for item in events] == ["sys.task.completed"]
    finally:
        await engine.dispose()


async def test_handler_rejects_handler_outside_whitelist(tmp_path: Path) -> None:
    """执行体不在白名单：返回不可重试失败并回写 failed（不执行任意代码）。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'task.log2.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(conn, tables=[SysTaskLog.__table__, SysOutbox.__table__])
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        log = SysTaskLog(task_id=2, run_id="r2", trigger_source="schedule", status=TASK_RUN_RUNNING, retry_count=0)
        session.add(log)
        await session.flush()
        log_id = int(log.id)

    @asynccontextmanager
    async def _open() -> Any:
        async with maker() as session:
            yield session

    ctx = JobContext(
        job_id=101,
        job_type="sys.task.run",
        service_key="platform",
        db_key="platform",
        payload=ConcurrentStableDict(
            {
                "task_id": 2,
                "log_id": log_id,
                "run_id": "r2",
                "code": "evil",
                "handler": "os.system:system",
                "args_json": None,
            }
        ),
        open_session=_open,
    )
    try:
        result = await TaskJobHandler().run(ctx)
        assert result.status == "failed"
        assert result.retryable is False
        async with maker() as session:
            row = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalars().one()
        assert row.status == "failed"
        assert row.error_msg
    finally:
        await engine.dispose()


_ = DbSession
