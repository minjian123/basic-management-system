"""作业提交与同步内联护栏（Kiwi 2375 / 2379 / 2380 / 2382）：run_inline / 幂等 / 终态 / 重试。"""

import pytest
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import JobTypeNotRegisteredError
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission, JobTypeSpec
from bms_core.models.job import SysJob, SysJobError
from bms_core.models.outbox import SysOutbox

pytestmark = pytest.mark.kiwi_id(2382)


class _Echo(BaseJobHandler):
    job_type = "demo.echo"

    async def run(self, ctx: JobContext) -> JobResult:
        await ctx.report_progress(1, 2)
        await ctx.add_error("demo warning", row_no=2, column_key="name")
        await ctx.report_progress(2, 2)
        return JobResult.success(ConcurrentStableDict({"echo": ctx.payload.get("n")}))


class _FailNoRetry(BaseJobHandler):
    job_type = "demo.fail"

    async def run(self, ctx: JobContext) -> JobResult:
        _ = ctx
        return JobResult.failed("boom", retryable=False)


class _Cancel(BaseJobHandler):
    job_type = "demo.cancel"

    async def run(self, ctx: JobContext) -> JobResult:
        _ = ctx
        return JobResult.canceled("用户取消")


class _Explode(BaseJobHandler):
    job_type = "demo.explode"

    async def run(self, ctx: JobContext) -> JobResult:
        _ = ctx
        raise RuntimeError("explode")


def _runner() -> JobRunner:
    """构造带四种 handler 的提交器。

    Returns:
        JobRunner: 提交器。
    """
    registry = JobHandlerRegistry()
    registry.load(
        {
            "demo.echo": _Echo(),
            "demo.fail": _FailNoRetry(),
            "demo.cancel": _Cancel(),
            "demo.explode": _Explode(),
        }
    )
    specs = {
        name: JobTypeSpec(job_type=name, service_key="platform", domain_key="job", max_attempts=1)
        for name in ("demo.echo", "demo.fail", "demo.cancel", "demo.explode")
    }
    return JobRunner(registry=registry, specs=specs, limits=JobLimits())


async def test_run_inline_success(session) -> None:
    """同步内联：同一记录、进度、行级错误与终态；事件覆盖提交 / 进度 / 完成。"""
    runner = _runner()
    async with session.begin():
        record, result = await runner.run_inline(
            session,
            JobSubmission(job_type="demo.echo", payload=ConcurrentStableDict({"n": 7})),
            db_key="platform",
        )
    assert result.status == "succeeded"
    assert record.status == "succeeded"
    assert record.progress_done == 2 and record.progress_total == 2
    async with session.begin():
        errors = (await session.execute(select(SysJobError))).scalars().all()
        events = {item.event_type for item in (await session.execute(select(SysOutbox))).scalars().all()}
    assert len(errors) == 1
    assert {"sys.job.submitted", "sys.job.progress", "sys.job.completed"} <= events


async def test_run_inline_idempotent(session) -> None:
    """同幂等键再次内联：返回既有作业，不重复执行。"""
    runner = _runner()
    submission = JobSubmission(
        job_type="demo.echo", payload=ConcurrentStableDict({"n": 1}), idempotency_key="same"
    )
    async with session.begin():
        first, _ = await runner.run_inline(session, submission, db_key="platform")
    async with session.begin():
        second, result = await runner.run_inline(session, submission, db_key="platform")
    assert second.id == first.id
    assert "幂等命中" in result.message


async def test_run_inline_failed_not_retryable(session) -> None:
    """不可重试失败：终态 failed。"""
    async with session.begin():
        record, result = await _runner().run_inline(
            session, JobSubmission(job_type="demo.fail"), db_key="platform"
        )
    assert result.status == "failed"
    assert record.status == "failed"


async def test_run_inline_exception_exhausts_to_dead(session) -> None:
    """异常按可重试处理；attempts 达上限即死信。"""
    async with session.begin():
        record, result = await _runner().run_inline(
            session, JobSubmission(job_type="demo.explode"), db_key="platform"
        )
    assert result.status == "failed"
    assert record.status == "dead"
    async with session.begin():
        left = (await session.execute(select(SysJob))).scalars().all()
    assert len(left) == 1


async def test_run_inline_canceled(session) -> None:
    """handler 返回取消：终态 canceled。"""
    async with session.begin():
        record, result = await _runner().run_inline(
            session, JobSubmission(job_type="demo.cancel"), db_key="platform"
        )
    assert result.status == "canceled"
    assert record.status == "canceled"


async def test_submit_unknown_type(session) -> None:
    """未声明类型：抛 71002。

    Raises:
        JobTypeNotRegisteredError: 期望抛出。
    """
    async with session.begin():
        with pytest.raises(JobTypeNotRegisteredError):
            await _runner().submit(session, JobSubmission(job_type="demo.missing"))
