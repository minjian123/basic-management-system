"""作业消费者护栏（Kiwi 2377 / 2378 / 2379 / 2380 / 2381）：抢占 / 执行 / 事件 / 回收 / 并发 / 停机。"""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.registry import EngineRegistry
from bms_core.jobs import store
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.spec import JobSubmission, JobTypeSpec, now_utc
from bms_core.jobs.worker import JobWorker
from bms_core.models.job import SysJob
from bms_core.models.outbox import SysOutbox

pytestmark = pytest.mark.kiwi_id(2377)


class _Counting(BaseJobHandler):
    job_type = "demo.count"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, ctx: JobContext) -> JobResult:
        self.calls += 1
        await ctx.report_progress(1, 1)
        return JobResult.success(ConcurrentStableDict({"calls": self.calls}))


async def _keys() -> ConcurrentStableList[str]:
    """单库键提供者。

    Returns:
        ConcurrentStableList[str]: 库键清单。
    """
    return ConcurrentStableList(["platform"])


def _worker(registry: EngineRegistry, handler: _Counting, *, worker_id: str = "w1") -> JobWorker:
    """构造单 handler worker。

    Args:
        registry: 引擎注册表。
        handler: 计数 handler。
        worker_id: 执行者标识。

    Returns:
        JobWorker: worker。
    """
    handlers = JobHandlerRegistry()
    handlers.load({handler.job_type: handler})
    specs: dict[str, JobTypeSpec] = {
        handler.job_type: JobTypeSpec(job_type=handler.job_type, service_key="platform", domain_key="job")
    }
    return JobWorker(
        service_key="platform",
        registry=handlers,
        specs=specs,
        limits=JobLimits(),
        engine_registry=registry,
        db_keys=_keys,
        worker_id=worker_id,
    )


async def _submit(session: AsyncSession, *, key: str | None = None, max_attempts: int = 2) -> int:
    """提交一条作业。

    Args:
        session: 会话。
        key: 幂等键。
        max_attempts: 最大执行次数。

    Returns:
        int: 作业主键。
    """
    async with session.begin():
        record, _ = await store.submit_job(
            session,
            submission=JobSubmission(
                job_type="demo.count", payload=ConcurrentStableDict({"n": 1}), idempotency_key=key
            ),
            service_key="platform",
            domain_key="job",
            max_attempts=max_attempts,
        )
        return int(record.id)


async def test_tick_executes_and_emits_events(session: AsyncSession, registry: EngineRegistry) -> None:
    """单轮：抢占、执行、进度、终态与 started / progress / completed 事件。"""
    handler = _Counting()
    await _submit(session)
    report = await _worker(registry, handler).tick()
    assert report.claimed == 1 and report.executed == 1
    assert handler.calls == 1
    async with session.begin():
        record = (await session.execute(select(SysJob))).scalars().one()
        events = {item.event_type for item in (await session.execute(select(SysOutbox))).scalars().all()}
    assert record.status == "succeeded"
    assert {"sys.job.started", "sys.job.progress", "sys.job.completed"} <= events


async def test_two_workers_claim_once(session: AsyncSession, registry: EngineRegistry) -> None:
    """两个 worker 同时 tick：同一作业只执行一次（条件 UPDATE CAS）。"""
    first_handler = _Counting()
    second_handler = _Counting()
    await _submit(session)
    first = _worker(registry, first_handler, worker_id="w1")
    second = _worker(registry, second_handler, worker_id="w2")
    await asyncio.gather(first.tick(), second.tick())
    assert first_handler.calls + second_handler.calls == 1


async def test_tick_reclaims_expired_lease(session: AsyncSession, registry: EngineRegistry) -> None:
    """租约过期的运行中作业被回收并重新执行。"""
    handler = _Counting()
    job_id = await _submit(session)
    past = now_utc() - timedelta(seconds=10)
    async with session.begin():
        await store.claim_job(session, job_id=job_id, worker_id="dead", lease_until=past, now=past)
    report = await _worker(registry, handler).tick()
    assert report.requeued == 1
    assert handler.calls == 1
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None and record.status == "succeeded"


async def test_aclose_waits_inflight(session: AsyncSession, registry: EngineRegistry) -> None:
    """停机：置标志并在在途完成后返回。"""
    handler = _Counting()
    worker = _worker(registry, handler)
    await worker.aclose()
    assert worker.stopping is True
    report = await worker.tick()
    assert report.claimed == 0


async def test_worker_rejects_missing_handler(registry: EngineRegistry) -> None:
    """声明存在但代码侧 handler 缺失：构造即拒（71006）。

    Raises:
        JobHandlerNotRegisteredError: 期望抛出。
    """
    from bms_core.core.exceptions import JobHandlerNotRegisteredError

    with pytest.raises(JobHandlerNotRegisteredError):
        JobWorker(
            service_key="platform",
            registry=JobHandlerRegistry(),
            specs={"demo.count": JobTypeSpec(job_type="demo.count", service_key="platform", domain_key="job")},
            limits=JobLimits(),
            engine_registry=registry,
            db_keys=_keys,
        )
