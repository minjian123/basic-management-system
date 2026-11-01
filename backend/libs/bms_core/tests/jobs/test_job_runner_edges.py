"""作业执行器边缘用例：超时 / 异常 / 上下文回调 / 进度节流 / 心跳 / 终态分支。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.jobs import store
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobExecutor, JobRunner
from bms_core.jobs.spec import JobSnapshot, JobSubmission, JobTypeSpec, now_utc

pytestmark = pytest.mark.kiwi_id(2382)


def _limits(**overrides: object) -> JobLimits:
    """构造参数（可覆盖字段）。"""
    limits = JobLimits()
    for key, value in overrides.items():
        object.__setattr__(limits, key, value)
    return limits


def _executor(session: AsyncSession, *, limits: JobLimits | None = None, heartbeat: bool = False) -> JobExecutor:
    """构造执行器（共享现有会话，不自开事务）。"""

    @asynccontextmanager
    async def _provider() -> AsyncGenerator[AsyncSession]:
        yield session

    return JobExecutor(
        limits=limits or _limits(),
        session_provider=_provider,
        worker_id="w1",
        heartbeat_enabled=heartbeat,
        transactional_writes=False,
        sleep=_noop_sleep,
    )


async def _noop_sleep(seconds: float) -> None:
    """睡眠替身。"""
    del seconds


def _snapshot(**overrides: object) -> JobSnapshot:
    """构造作业快照。"""
    fields: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "id": 1,
            "job_type": "demo.echo",
            "service_key": "platform",
            "domain_key": "job",
            "status": "running",
            "payload": ConcurrentStableDict[str, object](),
            "payload_version": "1.0.0",
            "attempts": 1,
            "max_attempts": 3,
            "db_key": "platform",
            "lease_owner": "w1",
        }
    )
    fields.update(overrides)
    return JobSnapshot(**dict(fields))  # type: ignore[arg-type]


class _Slow(BaseJobHandler):
    """超时 handler。"""

    job_type = "demo.slow"

    async def run(self, ctx: JobContext) -> JobResult:
        """等待足够久以触发超时。"""
        del ctx
        await asyncio.sleep(5)
        return JobResult.success()


class _BadStatus(BaseJobHandler):
    """返回非法状态。"""

    job_type = "demo.bad"

    async def run(self, ctx: JobContext) -> JobResult:
        """返回未定义状态。"""
        del ctx
        return JobResult(status="running")


class _Boom(BaseJobHandler):
    """抛异常 handler。"""

    job_type = "demo.boom"

    async def run(self, ctx: JobContext) -> JobResult:
        """抛异常。"""
        del ctx
        raise RuntimeError("boom")


async def test_invoke_timeout_exception_and_invalid_status() -> None:
    """调用语义：超时 / 系统异常可重试，非法状态不可重试；超时 0 表示不限。"""
    executor = _executor(cast("Any", None))
    context = JobContext(job_id=1, job_type="demo", service_key="platform", db_key="platform")
    timeout_result = await executor._invoke(_Slow(), context, 1)  # pyright: ignore[reportPrivateUsage]
    assert timeout_result.status == "failed" and timeout_result.retryable is True
    assert "执行超时" in timeout_result.message

    boom = await executor._invoke(_Boom(), context, 0)  # pyright: ignore[reportPrivateUsage]
    assert boom.status == "failed" and "RuntimeError" in boom.message

    bad = await executor._invoke(_BadStatus(), context, 0)  # pyright: ignore[reportPrivateUsage]
    assert bad.status == "failed" and bad.retryable is False


async def test_build_context_invokes_callbacks(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """上下文回调：会话 / 进度 / 取消 / 行级错误均转调到写口。"""
    executor = _executor(session)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _progress(snapshot: JobSnapshot, done: int, total: int | None) -> None:
        del snapshot, done, total
        calls.append("progress")

    async def _error(session_: AsyncSession, *, job_id: int, message: str, **kwargs: object) -> None:
        del session_, job_id, message, kwargs
        calls.append("error")

    monkeypatch.setattr(executor, "_report_progress", _progress)
    monkeypatch.setattr(store, "add_job_error", _error)
    context = executor._build_context(_snapshot())  # pyright: ignore[reportPrivateUsage]
    async with context.session() as opened:
        assert opened is session
    await context.report_progress(1, 2)
    assert await context.should_cancel() is False
    await context.add_error("bad", row_no=1)
    assert calls == ["progress", "error"]


async def test_report_progress_throttle_and_failure(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """进度：节流窗口内跳过；非终态且超窗写库；更新失败静默返回；异常只告警。"""
    executor = _executor(session, limits=_limits(progress_interval_seconds=60))
    executor._last_progress_at = asyncio.get_running_loop().time()  # pyright: ignore[reportPrivateUsage]
    await executor._report_progress(_snapshot(), 1, 10)  # pyright: ignore[reportPrivateUsage]

    executor._last_progress_at = None  # pyright: ignore[reportPrivateUsage]

    async def _not_updated(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "update_progress", _not_updated)
    await executor._report_progress(_snapshot(), 2, 10)  # pyright: ignore[reportPrivateUsage]

    async def _explode(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise RuntimeError("db down")

    monkeypatch.setattr(store, "update_progress", _explode)
    executor._last_progress_at = None  # pyright: ignore[reportPrivateUsage]
    await executor._report_progress(_snapshot(), 3, 10)  # pyright: ignore[reportPrivateUsage]


async def test_heartbeat_loop_branches(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """心跳：关闭直接返回；租约失效退出；异常只告警；取消上抛。"""
    executor = _executor(session, heartbeat=False)
    await executor._heartbeat_loop(_snapshot(), False)  # pyright: ignore[reportPrivateUsage]

    async def _dead(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "heartbeat", _dead)
    await asyncio.wait_for(executor._heartbeat_loop(_snapshot(), True), timeout=2)  # pyright: ignore[reportPrivateUsage]

    async def _explode(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise RuntimeError("redis down")

    monkeypatch.setattr(store, "heartbeat", _explode)
    await asyncio.wait_for(executor._heartbeat_loop(_snapshot(), True), timeout=2)  # pyright: ignore[reportPrivateUsage]

    class _CancelSleep:
        async def __call__(self, seconds: float) -> None:
            del seconds
            raise asyncio.CancelledError()

    executor._sleep = cast("Any", _CancelSleep())  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(asyncio.CancelledError):
        await executor._heartbeat_loop(_snapshot(), True)  # pyright: ignore[reportPrivateUsage]


async def test_finalize_retryable_dead_and_backoff(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """终态：不可重试落 failed；次数用尽落 dead；否则按退避回队。"""
    requeued: ConcurrentStableList[tuple[int, Any]] = ConcurrentStableList()

    async def _requeue(session_: AsyncSession, *, job_id: int, next_run_at: Any, **kwargs: object) -> bool:
        del session_, kwargs
        requeued.append((job_id, next_run_at))
        return True

    monkeypatch.setattr(store, "requeue_job", _requeue)
    executor = _executor(session)
    await executor._finalize(_snapshot(), JobResult.failed("no", retryable=False), backoff_seconds=1)  # pyright: ignore[reportPrivateUsage]
    await executor._finalize(_snapshot(attempts=3, max_attempts=3), JobResult.failed("dead"), backoff_seconds=1)  # pyright: ignore[reportPrivateUsage]
    now = now_utc()
    executor._clock = lambda: now  # pyright: ignore[reportPrivateUsage]
    await executor._finalize(_snapshot(attempts=1, max_attempts=3), JobResult.failed("retry"), backoff_seconds=10)  # pyright: ignore[reportPrivateUsage]
    assert requeued and requeued[0][0] == 1
    assert requeued[0][1] > now


async def test_finish_skips_event_when_not_updated(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """终态写库未生效（已被他人收敛）：不写完成事件。"""

    async def _not_updated(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "finish_job", _not_updated)
    executor = _executor(session)
    await executor._finish(_snapshot(), "succeeded", now_utc())  # pyright: ignore[reportPrivateUsage]


async def test_run_inline_short_circuits(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """同步内联：幂等命中 / 非排队态 / 抢占失败均直接返回不执行。"""
    registry = JobHandlerRegistry()
    registry.load({_BadStatus.job_type: _BadStatus()})
    runner = JobRunner(
        registry=registry,
        specs={
            _BadStatus.job_type: JobTypeSpec(job_type=_BadStatus.job_type, service_key="platform", domain_key="job")
        },
        limits=_limits(),
    )

    class _Record:
        def __init__(self, status: str) -> None:
            self.status = status
            self.id = 1
            self.job_type = _BadStatus.job_type

    async def _submit(session_: AsyncSession, submission: JobSubmission, *, tenant_id: int | None = None) -> Any:
        del session_, submission, tenant_id
        return _Record("succeeded")

    monkeypatch.setattr(runner, "submit", _submit)
    _record, result = await runner.run_inline(session, JobSubmission(job_type=_BadStatus.job_type), db_key="platform")
    assert result.status == "succeeded" and "幂等命中" in result.message

    async def _submit_failed(session_: AsyncSession, submission: JobSubmission, *, tenant_id: int | None = None) -> Any:
        del session_, submission, tenant_id
        return _Record("weird")

    monkeypatch.setattr(runner, "submit", _submit_failed)
    _, failed = await runner.run_inline(session, JobSubmission(job_type=_BadStatus.job_type), db_key="platform")
    assert failed.status == "failed" and failed.retryable is False

    async def _submit_queued(session_: AsyncSession, submission: JobSubmission, *, tenant_id: int | None = None) -> Any:
        del session_, submission, tenant_id
        return _Record("queued")

    async def _not_claimed(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(runner, "submit", _submit_queued)
    monkeypatch.setattr(store, "claim_job", _not_claimed)
    _, lost = await runner.run_inline(session, JobSubmission(job_type=_BadStatus.job_type), db_key="platform")
    assert lost.status == "failed" and "已被其他执行者抢占" in lost.message


async def test_write_with_own_transaction(session: AsyncSession) -> None:
    """写口：自行开事务模式（worker）下进入 `session.begin()`。"""

    @asynccontextmanager
    async def _provider() -> AsyncGenerator[AsyncSession]:
        yield session

    executor = JobExecutor(
        limits=_limits(),
        session_provider=_provider,
        worker_id="w1",
        transactional_writes=True,
        sleep=_noop_sleep,
    )
    async with executor._write() as opened:  # pyright: ignore[reportPrivateUsage]
        assert opened is session


async def test_execute_cancels_heartbeat_task(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """执行：心跳开启时结束后取消心跳任务（覆盖 cancel + gather）。"""
    executor = _executor(session, heartbeat=True)
    monkeypatch.setattr(executor, "_finalize", _noop_finalize)
    result = await executor.execute(_BadStatus(), _snapshot(), timeout_seconds=0, backoff_seconds=0)
    assert result.status == "failed"


async def _noop_finalize(snapshot: JobSnapshot, result: JobResult, *, backoff_seconds: int) -> None:
    """终态收敛替身。"""
    del snapshot, result, backoff_seconds


async def test_invoke_reraises_cancelled() -> None:
    """调用：取消异常原样上抛（不转失败结果）。"""

    class _CancelHandler(BaseJobHandler):
        job_type = "demo.cancel_now"

        async def run(self, ctx: JobContext) -> JobResult:
            del ctx
            raise asyncio.CancelledError()

    executor = _executor(cast("Any", None))
    context = JobContext(job_id=1, job_type="demo", service_key="platform", db_key="platform")
    with pytest.raises(asyncio.CancelledError):
        await executor._invoke(_CancelHandler(), context, 0)  # pyright: ignore[reportPrivateUsage]


async def test_heartbeat_continues_while_alive(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """心跳：租约有效时继续下一轮，失效后退出。"""
    answers = [True, True, False]

    async def _heartbeat(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return answers.pop(0) if answers else False

    monkeypatch.setattr(store, "heartbeat", _heartbeat)
    executor = _executor(session)
    await asyncio.wait_for(executor._heartbeat_loop(_snapshot(), True), timeout=2)  # pyright: ignore[reportPrivateUsage]
    assert answers == []


async def test_runner_cancel_and_retry(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """提交器：取消与重试转调存储层。"""
    runner = JobRunner(
        registry=JobHandlerRegistry(),
        specs={},
        limits=_limits(),
    )

    async def _cancel(*args: object, **kwargs: object) -> str:
        del args, kwargs
        return "canceled"

    async def _retry(*args: object, **kwargs: object) -> Any:
        del args, kwargs
        return type("R", (), {"status": "retried"})()

    monkeypatch.setattr(store, "request_cancel", _cancel)
    monkeypatch.setattr(store, "retry_job", _retry)
    assert await runner.cancel(session, 1, reason="user") == "canceled"
    assert await runner.retry(session, 1) == "retried"
