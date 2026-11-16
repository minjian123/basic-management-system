"""真 Redis 集成护栏（Kiwi 2392）：唤醒信号跨进程往返 / 双 worker 竞争只执行一次。

未配置 `BMS_REDIS__URL` 时自动跳过（不计覆盖率分母）。

作业落点用共享平台库；作业类型按命名空间派生唯一值，用例结束删除本用例自造行。
"""

import asyncio
import os
from typing import Any
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.jobs import store
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.signal import JobChangeSignal
from bms_core.jobs.spec import JobSubmission, JobTypeSpec
from bms_core.jobs.worker import JobWorker
from bms_core.models.job import SysJob, SysJobError
from bms_core.testing.namespace import Namespace

pytestmark = [
    pytest.mark.kiwi_id(2392),
    pytest.mark.skipif(not os.environ.get("BMS_REDIS__URL"), reason="未配置真 Redis（BMS_REDIS__URL）"),
]


class _Counting(BaseJobHandler):
    job_type = "demo.real"

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, ctx: JobContext) -> JobResult:
        self.calls += 1
        return JobResult.success(ConcurrentStableDict({"calls": self.calls}))


def _counting_handler(name: str) -> _Counting:
    """按作业类型派生计数 handler（避免与其他用例的作业互相抢占）。

    Args:
        name: 本用例唯一作业类型。

    Returns:
        _Counting: 计数 handler。
    """

    class _NamedCounting(_Counting):
        job_type = name

    return _NamedCounting()


class _FakeRegistry:
    """最小引擎注册表替身（单库）。"""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def is_sync_only(self, key: str) -> bool:
        return False

    async def get(self, key: str, *, read_only: bool = False) -> object:
        return self._engine


async def _worker(engine: Any, handler: _Counting, worker_id: str, job_type: str) -> JobWorker:
    """构造单库 worker。

    Args:
        engine: 异步引擎。
        handler: 计数 handler。
        worker_id: 执行者标识。
        job_type: 作业类型。

    Returns:
        JobWorker: worker。
    """
    registry = JobHandlerRegistry()
    registry.load({job_type: handler})
    specs = {job_type: JobTypeSpec(job_type=job_type, service_key="platform", domain_key="job")}

    async def _keys() -> ConcurrentStableList[str]:
        return ConcurrentStableList(["platform"])

    return JobWorker(
        service_key="platform",
        registry=registry,
        specs=specs,
        limits=JobLimits(),
        engine_registry=_FakeRegistry(engine),  # type: ignore[arg-type]
        db_keys=_keys,
        worker_id=worker_id,
    )


async def test_signal_roundtrip() -> None:
    """真 Redis：发布后订阅协程被唤醒。"""
    client: Redis = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis 桩的 **kwargs 未标注
        os.environ["BMS_REDIS__URL"], decode_responses=False
    )
    channel = f"bms:test:job:{uuid4().hex}"
    signal = JobChangeSignal(client=client, channel=channel)
    event = asyncio.Event()
    task = asyncio.create_task(signal.wake_loop(event))
    try:
        await asyncio.sleep(0.2)
        assert await signal.publish() is True
        await asyncio.wait_for(event.wait(), timeout=3)
        assert event.is_set()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.aclose()


async def test_two_workers_execute_once(shared_platform_engine: AsyncEngine, ns: Namespace) -> None:
    """真 Redis 唤醒 + 两个 worker：同一作业只执行一次。"""
    job_type = f"demo.real{ns.prefix}"
    maker = async_sessionmaker(shared_platform_engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        job, _ = await store.submit_job(
            session,
            submission=JobSubmission(job_type=job_type, payload=ConcurrentStableDict({"n": 1})),
            service_key="platform",
            domain_key="job",
            max_attempts=2,
        )
    job_id = job.id
    first_handler = _counting_handler(job_type)
    second_handler = _counting_handler(job_type)
    first = await _worker(shared_platform_engine, first_handler, "real-w1", job_type)
    second = await _worker(shared_platform_engine, second_handler, "real-w2", job_type)
    try:
        await asyncio.gather(first.tick(), second.tick())
        assert first_handler.calls + second_handler.calls == 1
        async with maker() as session:
            row = (await session.execute(select(SysJob).where(SysJob.id == job_id))).scalars().one()
        assert row.status == "succeeded"
    finally:
        await first.aclose()
        await second.aclose()
        async with maker() as session:
            jobs = (await session.execute(select(SysJob).where(SysJob.id == job_id))).scalars().all()
            errors = (await session.execute(select(SysJobError).where(SysJobError.job_id == job_id))).scalars().all()
            for row in jobs:
                await session.delete(row)
            for row in errors:
                await session.delete(row)
            await session.commit()
