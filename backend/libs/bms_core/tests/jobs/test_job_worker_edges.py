"""作业消费者边缘用例：停机等待 / 长驻循环 / 单库失败 / 超限转死信 / 指标。"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.registry import EngineRegistry
from bms_core.jobs import store
from bms_core.jobs import worker as worker_module
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.spec import JobSubmission, JobTypeSpec
from bms_core.jobs.worker import JobWorker
from bms_core.models.job import SysJob

pytestmark = pytest.mark.kiwi_id(2377)


class _Handler(BaseJobHandler):
    """示例 handler。"""

    job_type = "demo.count"

    async def run(self, ctx: JobContext) -> JobResult:
        """返回成功。"""
        del ctx
        return JobResult.success()


class _Metrics:
    """指标记录器替身。"""

    def __init__(self) -> None:
        self.counters: ConcurrentStableList[tuple[str, float]] = ConcurrentStableList()
        self.histograms: ConcurrentStableList[tuple[str, float]] = ConcurrentStableList()

    async def counter(self, name: str, *, value: float = 1.0, labels: object = None) -> None:
        """记录计数。"""
        del labels
        self.counters.append((name, value))

    async def histogram(self, name: str, *, value: float, labels: object = None) -> None:
        """记录直方图。"""
        del labels
        self.histograms.append((name, value))


def _fast_limits() -> JobLimits:
    """宽限期与轮询间隔取 0（测试不等待）。"""
    limits = JobLimits()
    object.__setattr__(limits, "shutdown_grace_seconds", 0)
    object.__setattr__(limits, "poll_interval_seconds", 0.0)
    return limits


def _worker(registry: EngineRegistry, **overrides: object) -> JobWorker:
    """构造 worker（默认单 handler）。"""
    handlers = JobHandlerRegistry()
    handlers.load({_Handler.job_type: _Handler()})
    options: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "service_key": "platform",
            "registry": handlers,
            "specs": {
                _Handler.job_type: JobTypeSpec(job_type=_Handler.job_type, service_key="platform", domain_key="job")
            },
            "limits": _fast_limits(),
            "engine_registry": registry,
            "db_keys": _keys,
        }
    )
    options.update(overrides)
    return JobWorker(**dict(options))  # type: ignore[arg-type]


async def _keys() -> ConcurrentStableList[str]:
    """单库键。"""
    return ConcurrentStableList(["platform"])


async def _submit(session: AsyncSession, *, max_attempts: int = 2) -> int:
    """提交一条作业。"""
    async with session.begin():
        record, _ = await store.submit_job(
            session,
            submission=JobSubmission(job_type=_Handler.job_type, payload=ConcurrentStableDict()),
            service_key="platform",
            domain_key="job",
            max_attempts=max_attempts,
        )
        return int(record.id)


async def test_aclose_waits_inflight_tasks(registry: EngineRegistry) -> None:
    """停机：在途任务完成后再返回。"""
    worker = _worker(registry)
    finished = asyncio.Event()

    async def _work() -> None:
        await finished.wait()

    task = asyncio.create_task(_work())
    worker._inflight.add(task)  # pyright: ignore[reportPrivateUsage]
    closer = asyncio.create_task(worker.aclose())
    await asyncio.sleep(0)
    assert not closer.done()
    finished.set()
    await asyncio.wait_for(closer, timeout=2)
    assert worker.stopping is True


async def test_aclose_cancels_after_grace(registry: EngineRegistry) -> None:
    """停机：超过宽限期仍未完成的任务被取消。"""
    worker = _worker(registry, limits=_fast_limits())
    never = asyncio.Event()

    async def _work() -> None:
        await never.wait()

    task = asyncio.create_task(_work())
    worker._inflight.add(task)  # pyright: ignore[reportPrivateUsage]
    await asyncio.wait_for(worker.aclose(), timeout=2)
    assert task.cancelled()


async def test_run_forever_exits_after_stop(registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """长驻：tick 一轮后等待唤醒，置停止标志即退出（唤醒协程被取消）。"""

    class _Signal:
        async def wake_loop(self, event: asyncio.Event) -> None:
            event.set()

    worker = _worker(registry, signal=cast("Any", _Signal()))
    run = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.05)
    await worker.aclose()
    await asyncio.wait_for(run, timeout=2)


async def test_tick_continues_when_one_db_fails(registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """单库抢占异常不拖垮其他库。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _keys() -> ConcurrentStableList[str]:
        return ConcurrentStableList(["bad", "good"])

    worker = _worker(registry, db_keys=_keys)

    async def _round(db_key: str) -> tuple[ConcurrentStableList[Any], int, int]:
        calls.append(db_key)
        if db_key == "bad":
            raise RuntimeError("db down")
        return ConcurrentStableList(), 0, 0

    monkeypatch.setattr(worker, "_claim_round", _round)
    report = await worker.tick()
    assert calls == ["bad", "good"]
    assert report.claimed == 0


async def test_claim_round_marks_dead_before_claim(
    session: AsyncSession, registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """候选已用尽次数：抢占前直接转死信，不进入执行。"""
    job_id = await _submit(session, max_attempts=1)
    async with session.begin():
        await session.execute(update(SysJob).where(SysJob.id == job_id).values(attempts=1, status="queued"))
    worker = _worker(registry)
    report = await worker.tick()
    assert report.dead == 1 and report.claimed == 0
    async with session.begin():
        record = await store.get_job(session, job_id)
    assert record is not None and record.status == "dead"


async def test_tick_skips_unclaimed_and_missing_record(
    session: AsyncSession, registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """抢占失败 / 记录消失：跳过并继续下一候选。"""
    await _submit(session)
    worker = _worker(registry)

    async def _not_claimed(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "claim_job", _not_claimed)
    report = await worker.tick()
    assert report.claimed == 0

    async def _claimed(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return True

    async def _missing(*args: object, **kwargs: object) -> None:
        del args, kwargs
        return None

    monkeypatch.setattr(store, "claim_job", _claimed)
    monkeypatch.setattr(store, "get_job", _missing)
    assert (await worker.tick()).claimed == 0


async def test_tick_and_run_record_metrics(
    session: AsyncSession, registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """指标：抢占与执行分别记计数 / 直方图。"""
    metrics = _Metrics()
    await _submit(session)
    worker = _worker(registry, metrics=cast("Any", metrics))
    report = await worker.tick()
    assert report.executed == 1
    names = [name for name, _value in metrics.counters]
    assert "bms_job_claimed_total" in names
    assert "bms_job_run_total" in names
    assert metrics.histograms


async def test_execute_one_returns_false_when_stopping(registry: EngineRegistry) -> None:
    """并发等待期间停机：不执行并返回 False。"""
    worker = _worker(registry)
    await worker.aclose()
    snapshot = cast(
        "Any",
        type("S", (), {"tenant_id": None, "job_type": _Handler.job_type, "id": 1, "service_key": "platform"})(),
    )
    assert await worker._execute_one(snapshot) is False  # pyright: ignore[reportPrivateUsage]


async def test_properties_run_once_and_stopped_tick(registry: EngineRegistry) -> None:
    """属性与短跑：`worker_id` 可读；`run_once` 等价 tick；停止后 tick 返回空。"""
    worker = _worker(registry)
    assert worker.worker_id == "platform-" + worker.worker_id.split("-", 1)[1]
    report = await worker.run_once()
    assert report.claimed == 0
    await worker.aclose()
    stopped = await worker.tick()
    assert stopped.claimed == 0 and stopped.executed == 0


async def test_run_forever_without_signal(registry: EngineRegistry) -> None:
    """长驻：未注入信号时只按周期轮询，置停止即退出。"""
    limits = _fast_limits()
    object.__setattr__(limits, "poll_interval_seconds", 0.01)
    worker = _worker(registry, limits=limits)
    run = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.03)
    await worker.aclose()
    await asyncio.wait_for(run, timeout=2)


async def test_claim_round_skips_when_mark_dead_false(
    session: AsyncSession, registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """候选超限但 mark_dead 未生效（被他人处理）：不计数。"""
    job_id = await _submit(session, max_attempts=1)
    async with session.begin():
        await session.execute(update(SysJob).where(SysJob.id == job_id).values(attempts=1, status="queued"))

    async def _false(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        return False

    monkeypatch.setattr(store, "mark_dead", _false)
    report = await _worker(registry).tick()
    assert report.dead == 0 and report.claimed == 0


async def test_execute_one_reuses_semaphores(registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """并发约束：同一租户 / 类型复用已建信号量；任务完成后从在途清单移除。"""
    worker = _worker(registry)
    ran: ConcurrentStableList[int] = ConcurrentStableList()

    async def _run_one(snapshot: Any, spec: Any) -> None:
        del spec
        ran.append(snapshot.id)

    monkeypatch.setattr(worker, "_run_one", _run_one)
    snapshot = cast(
        "Any", type("S", (), {"tenant_id": 9, "job_type": _Handler.job_type, "id": 1, "service_key": "platform"})()
    )
    assert await worker._execute_one(snapshot) is True  # pyright: ignore[reportPrivateUsage]
    assert await worker._execute_one(snapshot) is True  # pyright: ignore[reportPrivateUsage]
    assert ran == [1, 1]
    assert worker._tenant_semaphores.get("9") is not None  # pyright: ignore[reportPrivateUsage]
    assert worker._inflight == []  # pyright: ignore[reportPrivateUsage]


def test_worker_rejects_missing_handler(registry: EngineRegistry) -> None:
    """声明存在但代码侧 handler 缺失：构造即拒。"""
    from bms_core.core.exceptions import JobHandlerNotRegisteredError

    with pytest.raises(JobHandlerNotRegisteredError):
        JobWorker(
            service_key="platform",
            registry=JobHandlerRegistry(),
            specs={
                _Handler.job_type: JobTypeSpec(job_type=_Handler.job_type, service_key="platform", domain_key="job")
            },
            limits=_fast_limits(),
            engine_registry=registry,
            db_keys=_keys,
        )


async def test_execute_one_when_task_already_removed(registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """在途清单被并发清理：finally 不重复移除。"""
    worker = _worker(registry)

    async def _run_one(snapshot: Any, spec: Any) -> None:
        del snapshot, spec
        worker._inflight = ConcurrentStableList()  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(worker, "_run_one", _run_one)
    snapshot = cast(
        "Any", type("S", (), {"tenant_id": None, "job_type": _Handler.job_type, "id": 1, "service_key": "platform"})()
    )
    assert await worker._execute_one(snapshot) is True  # pyright: ignore[reportPrivateUsage]


async def test_run_one_without_spec_and_failure_log(registry: EngineRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """未声明类型：取默认超时 / 退避；失败结果记告警日志。"""

    class _Executor:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def execute(self, *args: object, **kwargs: object) -> JobResult:
            del args, kwargs
            return JobResult.failed("boom")

    monkeypatch.setattr(worker_module, "JobExecutor", _Executor)
    worker = _worker(registry)
    snapshot = cast(
        "Any", type("S", (), {"tenant_id": None, "job_type": _Handler.job_type, "id": 1, "service_key": "platform"})()
    )
    await worker._run_one(snapshot, None)  # pyright: ignore[reportPrivateUsage]
