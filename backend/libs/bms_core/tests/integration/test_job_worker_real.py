"""真 Redis 集成护栏（Kiwi 2392）：唤醒信号跨进程往返 / 双 worker 竞争只执行一次。

未配置 `BMS_REDIS__URL` 时自动跳过（不计覆盖率分母）。
"""

import asyncio
import os
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.jobs import store
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.signal import JobChangeSignal
from bms_core.jobs.spec import JobSubmission, JobTypeSpec
from bms_core.jobs.worker import JobWorker
from bms_core.models.base import Base
from bms_core.models.job import SysJob, SysJobError
from bms_core.models.outbox import SysOutbox

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


class _FakeRegistry:
    """最小引擎注册表替身（单库 SQLite）。"""

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    def is_sync_only(self, key: str) -> bool:
        return False

    async def get(self, key: str, *, read_only: bool = False) -> object:
        return self._engine


async def _worker(engine: Any, handler: _Counting, worker_id: str) -> JobWorker:
    """构造单库 worker。

    Args:
        engine: 异步引擎。
        handler: 计数 handler。
        worker_id: 执行者标识。

    Returns:
        JobWorker: worker。
    """
    registry = JobHandlerRegistry()
    registry.load({handler.job_type: handler})
    specs = {"demo.real": JobTypeSpec(job_type="demo.real", service_key="platform", domain_key="job")}

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


async def test_two_workers_execute_once(tmp_path: Path) -> None:
    """真 Redis 唤醒 + 两个 worker：同一作业只执行一次。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'real.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn,
                tables=[
                    cast("Table", SysJob.__table__),
                    cast("Table", SysJobError.__table__),
                    cast("Table", SysOutbox.__table__),
                ],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        await store.submit_job(
            session,
            submission=JobSubmission(job_type="demo.real", payload=ConcurrentStableDict({"n": 1})),
            service_key="platform",
            domain_key="job",
            max_attempts=2,
        )
    first_handler = _Counting()
    second_handler = _Counting()
    first = await _worker(engine, first_handler, "real-w1")
    second = await _worker(engine, second_handler, "real-w2")
    try:
        await asyncio.gather(first.tick(), second.tick())
        assert first_handler.calls + second_handler.calls == 1
        async with maker() as session:
            row = (await session.execute(select(SysJob))).scalars().one()
        assert row.status == "succeeded"
    finally:
        await first.aclose()
        await second.aclose()
        await engine.dispose()
