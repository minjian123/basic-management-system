"""任务执行作业边缘用例：执行体异常 / 成功 / 失败态与负载解析。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.jobs.base import JobContext
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.task import TASK_RUN_RUNNING, SysTaskLog
from bms_core.tasks.spec import TaskResult
from bms_platform.domains.task import jobs as task_jobs
from bms_platform.domains.task.jobs import TaskJobHandler

pytestmark = pytest.mark.kiwi_id(2383)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncGenerator[AsyncSession]:
    """建任务日志与发件箱两表并开会话。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'taskjobs.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[cast("Table", SysTaskLog.__table__), cast("Table", SysOutbox.__table__)],
            )
        )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as opened:
        yield opened
    await engine.dispose()


async def _context(session: AsyncSession, *, task_id: int = 1) -> tuple[JobContext, int]:
    """建一条运行中的任务日志并构造执行上下文。"""
    async with session.begin():
        log = SysTaskLog(task_id=task_id, run_id="r", trigger_source="schedule", status=TASK_RUN_RUNNING, retry_count=0)
        session.add(log)
        await session.flush()
        log_id = int(log.id)

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        async with session.begin():
            yield session

    ctx = JobContext(
        job_id=100,
        job_type="sys.task.run",
        service_key="platform",
        db_key="platform",
        payload=ConcurrentStableDict(
            {
                "task_id": task_id,
                "log_id": log_id,
                "run_id": "r",
                "code": "demo",
                "handler": "bms_core.tasks.builtin:run_archive_audit_logs",
                "args_json": None,
            }
        ),
        open_session=_open,
    )
    return ctx, log_id


async def test_handler_exception_returns_retryable_failure(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """执行体抛系统异常：作业可重试（留待下次尝试 / 超时回收）。"""

    async def _boom(ctx: Any) -> TaskResult:
        del ctx
        raise RuntimeError("boom")

    def _resolve(path: str, prefixes: object) -> Any:
        del path, prefixes
        return _boom

    monkeypatch.setattr(task_jobs, "resolve_handler", _resolve)
    ctx, _ = await _context(session)
    result = await TaskJobHandler().run(ctx)
    assert result.status == "failed" and result.retryable is True
    assert "RuntimeError" in result.message


async def test_handler_success_returns_job_success(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """执行体返回成功：作业成功并带任务 / 日志标识。"""

    async def _ok(ctx: Any) -> TaskResult:
        del ctx
        return TaskResult(status="success", message="ok")

    def _resolve(path: str, prefixes: object) -> Any:
        del path, prefixes
        return _ok

    monkeypatch.setattr(task_jobs, "resolve_handler", _resolve)
    ctx, _ = await _context(session, task_id=2)
    result = await TaskJobHandler().run(ctx)
    assert result.status == "succeeded"
    assert result.output is not None and result.output["task_id"] == "2"


async def test_handler_failed_returns_non_retryable(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """执行体返回失败：作业不可重试（业务失败不反复提交）。"""

    async def _failed(ctx: Any) -> TaskResult:
        del ctx
        return TaskResult(status="failed", message="业务失败")

    def _resolve(path: str, prefixes: object) -> Any:
        del path, prefixes
        return _failed

    monkeypatch.setattr(task_jobs, "resolve_handler", _resolve)
    ctx, _ = await _context(session, task_id=3)
    result = await TaskJobHandler().run(ctx)
    assert result.status == "failed" and result.retryable is False
    assert result.message == "业务失败"


def test_optional_int_branches() -> None:
    """负载租户主键：空值返回 None，其余转 int。"""
    assert task_jobs._optional_int(None) is None  # pyright: ignore[reportPrivateUsage]
    assert task_jobs._optional_int("") is None  # pyright: ignore[reportPrivateUsage]
    assert task_jobs._optional_int("9") == 9  # pyright: ignore[reportPrivateUsage]


async def test_finish_opens_own_transaction(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """执行体返回时会话无事务：终态写口自行开启事务并提交。"""

    async def _ok(ctx: Any) -> TaskResult:
        del ctx
        return TaskResult(status="success", message="ok")

    def _resolve(path: str, prefixes: object) -> Any:
        del path, prefixes
        return _ok

    monkeypatch.setattr(task_jobs, "resolve_handler", _resolve)
    async with session.begin():
        log = SysTaskLog(task_id=4, run_id="r4", trigger_source="schedule", status=TASK_RUN_RUNNING, retry_count=0)
        session.add(log)
        await session.flush()
        log_id = int(log.id)

    @asynccontextmanager
    async def _open() -> AsyncGenerator[AsyncSession]:
        yield session

    ctx = JobContext(
        job_id=104,
        job_type="sys.task.run",
        service_key="platform",
        db_key="platform",
        payload=ConcurrentStableDict(
            {
                "task_id": 4,
                "log_id": log_id,
                "run_id": "r4",
                "code": "demo",
                "handler": "bms_core.tasks.builtin:run_archive_audit_logs",
                "args_json": None,
            }
        ),
        open_session=_open,
    )
    result = await TaskJobHandler().run(ctx)
    assert result.status == "succeeded"
