"""调度器迁移护栏（01_03）：锁互斥 / 到期抢占并提交 `sys.task.run` 作业 / 不重复提交 / cron 失效停用 /
提交失败 / 超时回收 / 租户隔离。

执行本身由 `tests/jobs/test_job_worker.py` 与 `test_task_migration.py` 覆盖；本文件只测 beat 侧。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobTypeSpec
from bms_core.lock.base import DEFAULT_WAIT, BaseDistributedLock
from bms_core.metrics.null import NullMetrics
from bms_core.models.job import SysJob
from bms_core.models.platform.task import (
    TASK_RUN_RUNNING,
    TASK_STATUS_DISABLED,
    SysTask,
    SysTaskLog,
)
from bms_core.tasks import scheduler as scheduler_module
from bms_core.tasks.scheduler import BEAT_LOCK_RESOURCE, TASK_RUN_JOB_TYPE, TaskScheduler, TenantDbRef, TickReport

pytestmark = pytest.mark.kiwi_id(2383)

NOW = datetime(2026, 11, 1, 3, 0, 0)
"""固定时钟（naive UTC），保证断言可复现。"""


class _StubLock(BaseDistributedLock):
    """可编排的锁替身（默认取锁成功）。"""

    def __init__(self, token: str | None = "token") -> None:
        """初始化。

        Args:
            token: 取锁返回值（None 表示被他人持有）。
        """
        self._token = token
        self.released: ConcurrentStableList[str] = ConcurrentStableList()

    async def acquire(self, key: str, *, ttl: int = 30, wait: float = DEFAULT_WAIT) -> str | None:
        """取锁（按构造时的返回值）。

        Args:
            key: 锁键。
            ttl: TTL（忽略）。
            wait: 等待时长（忽略）。

        Returns:
            str | None: 令牌或 None。
        """
        _ = (key, ttl, wait)
        return self._token

    async def release(self, key: str, token: str) -> bool:
        """释放锁并记录。

        Args:
            key: 锁键。
            token: 令牌。

        Returns:
            bool: 恒 True。
        """
        _ = token
        self.released.append(key)
        return True

    async def extend(self, key: str, token: str, *, ttl: int = 30) -> bool:
        """续租（替身恒成功）。

        Args:
            key: 锁键。
            token: 令牌。
            ttl: TTL。

        Returns:
            bool: 恒 True。
        """
        _ = (key, token, ttl)
        return True


def _keys(*db_keys: str) -> Any:
    """构造租户库键提供者。

    Args:
        *db_keys: 库键清单。

    Returns:
        Any: 异步可调用对象。
    """

    async def _provider() -> ConcurrentStableList[TenantDbRef]:
        return ConcurrentStableList(TenantDbRef(db_key=key, tenant_id=1) for key in db_keys)

    return _provider


def _runner() -> JobRunner:
    """构造作业提交器（`sys.task.run` 声明）。

    Returns:
        JobRunner: 提交器。
    """
    spec = JobTypeSpec(job_type=TASK_RUN_JOB_TYPE, service_key="platform", domain_key="task")
    return JobRunner(
        registry=JobHandlerRegistry(),
        specs={TASK_RUN_JOB_TYPE: spec},
        limits=JobLimits(),
        clock=lambda: NOW,
    )


def _scheduler(
    registry: EngineRegistry,
    *,
    runner: JobRunner | None = None,
    lock: BaseDistributedLock | None = None,
    tenants: ConcurrentStableList[str] | None = None,
    metrics: Any = None,
    poll_interval: float = 30.0,
) -> TaskScheduler:
    """构造调度器（固定时钟）。

    Args:
        registry: 引擎注册表。
        runner: 作业提交器。
        lock: 锁（缺省取锁成功替身）。
        tenants: 租户库键。
        metrics: 指标器。
        poll_interval: 轮询间隔。

    Returns:
        TaskScheduler: 调度器。
    """
    settings = TaskSchedulerSettings(poll_interval_seconds=poll_interval)
    return TaskScheduler(
        settings=settings,
        registry=registry,
        runner=runner if runner is not None else _runner(),
        lock=lock if lock is not None else _StubLock(),
        tenant_keys=_keys(*(tenants if tenants is not None else ConcurrentStableList(["platform"]))),
        signal=None,
        session_factory=SessionFactory(),
        metrics=metrics,
        clock=lambda: NOW,
    )


async def _add_task(
    session: AsyncSession,
    *,
    code: str = "task_a",
    cron: str = "0 3 * * *",
    next_run_at: datetime | None = None,
    status: str = "enabled",
) -> int:
    """插入一条任务定义。

    Args:
        session: 会话。
        code: 任务代码。
        cron: 调度表达式。
        next_run_at: 下次到期时间。
        status: 状态。

    Returns:
        int: 任务主键。
    """
    async with session.begin():
        task = SysTask(
            code=code,
            name=code,
            handler=f"bms_core.tasks.builtin:run_{code}",
            cron=cron,
            status=status,
            enabled=status == "enabled",
            next_run_at=next_run_at,
        )
        session.add(task)
        await session.flush()
        return int(task.id)


def test_lock_key_is_global_beat() -> None:
    """锁键固定为 `bms:global:lock:beat`（与架构口径一致）。"""
    assert BEAT_LOCK_RESOURCE == "beat"


async def test_tick_skips_when_lock_busy(registry: EngineRegistry, session: AsyncSession) -> None:
    """取不到锁即整轮跳过（另一实例在跑），且不派发。"""
    await _add_task(session, next_run_at=None)
    report = await _scheduler(registry, lock=_StubLock(token=None)).tick()
    assert report.lock_held is False
    assert report.dispatched == 0
    async with session.begin():
        assert (await session.execute(select(SysJob))).scalars().all() == []


async def test_tick_submits_job_for_due_task(registry: EngineRegistry, session: AsyncSession) -> None:
    """到期任务被抢占、落 running 记录并提交 `sys.task.run` 作业；下一轮不再重复提交。"""
    task_id = await _add_task(session, next_run_at=None)
    lock = _StubLock()
    scheduler = _scheduler(registry, lock=lock)
    report = await scheduler.tick()
    assert report.lock_held is True
    assert report.dispatched == 1
    assert report.tenants[0].claimed == 1
    assert lock.released == [scheduler.lock_key]
    async with session.begin():
        task = (await session.execute(select(SysTask).where(SysTask.id == task_id))).scalar_one()
        assert task.next_run_at is not None and task.next_run_at > NOW
        logs = (await session.execute(select(SysTaskLog).where(SysTaskLog.task_id == task_id))).scalars().all()
        jobs = (await session.execute(select(SysJob))).scalars().all()
    assert len(logs) == 1
    assert logs[0].status == TASK_RUN_RUNNING
    assert len(jobs) == 1
    assert jobs[0].job_type == TASK_RUN_JOB_TYPE
    assert jobs[0].status == "queued"
    assert jobs[0].idempotency_key == f"task:{task_id}:{logs[0].id}"
    second = await scheduler.tick()
    assert second.dispatched == 0


async def test_tick_disables_task_with_uncomputable_cron(registry: EngineRegistry, session: AsyncSession) -> None:
    """cron 永不触发（2 月 30 日）：自动停用，避免每轮空转。"""
    task_id = await _add_task(session, cron="0 0 30 2 *", next_run_at=None)
    report = await _scheduler(registry).tick()
    assert report.dispatched == 0
    async with session.begin():
        task = (await session.execute(select(SysTask).where(SysTask.id == task_id))).scalar_one()
    assert task.status == TASK_STATUS_DISABLED
    assert task.next_run_at is None


async def test_tick_counts_submit_failure(
    registry: EngineRegistry, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """提交作业失败：计入 failed，执行记录仍留 running（待超时回收）。"""

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        _ = (args, kwargs)
        raise RuntimeError("job store down")

    monkeypatch.setattr(JobRunner, "submit", _boom)
    task_id = await _add_task(session, next_run_at=None)
    report = await _scheduler(registry).tick()
    assert report.dispatched == 0
    assert report.tenants[0].claimed == 1
    assert report.tenants[0].failed == 1
    async with session.begin():
        logs = (await session.execute(select(SysTaskLog).where(SysTaskLog.task_id == task_id))).scalars().all()
    assert logs[0].status == TASK_RUN_RUNNING


async def test_tick_reclaims_stale_running(registry: EngineRegistry, session: AsyncSession) -> None:
    """顺带回收超时 running 记录（worker 失联兜底）。"""
    task_id = await _add_task(session, next_run_at=None)
    async with session.begin():
        session.add(
            SysTaskLog(
                task_id=task_id,
                status=TASK_RUN_RUNNING,
                run_id="stale",
                started_at=NOW - timedelta(hours=2),
            )
        )
    report = await _scheduler(registry).tick()
    assert report.reclaimed == 1


async def test_tick_records_metrics(registry: EngineRegistry, session: AsyncSession) -> None:
    """装配指标器时记录派发计数（未装配则跳过）。"""
    await _add_task(session, next_run_at=None)
    report = await _scheduler(registry, metrics=NullMetrics()).tick()
    assert report.dispatched == 1


async def test_tick_isolates_tenant_failure(
    registry: EngineRegistry,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个租户库不可用时不拖垮其他租户。"""
    real_scope = scheduler_module.session_scope

    @asynccontextmanager
    async def _scope(
        registry_: EngineRegistry, *, db_key: str | None = None, factory: Any = None
    ) -> AsyncGenerator[Any]:
        if db_key == "boom":
            raise RuntimeError("db down")
        async with real_scope(registry_, db_key=db_key, factory=factory) as opened:
            yield opened

    monkeypatch.setattr(scheduler_module, "session_scope", _scope)
    await _add_task(session, next_run_at=None)
    report = await _scheduler(registry, tenants=ConcurrentStableList(["platform", "boom"])).tick()
    assert report.lock_held is True
    assert [item.db_key for item in report.tenants] == ["platform", "boom"]
    assert report.tenants[0].dispatched == 1
    assert report.tenants[1].dispatched == 0


async def test_run_forever_submits_once_then_idles(registry: EngineRegistry, session: AsyncSession) -> None:
    """长驻循环：首个 tick 提交，之后到期时间已推进故不再重复。"""
    await _add_task(session, next_run_at=None)
    scheduler = _scheduler(registry, poll_interval=0.02)
    task = asyncio.create_task(scheduler.run_forever())
    await asyncio.sleep(0.2)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    async with session.begin():
        jobs = (await session.execute(select(SysJob))).scalars().all()
    assert len(jobs) == 1


async def test_aclose_is_noop(registry: EngineRegistry) -> None:
    """释放钩子不持有长连接（可重复调用）。"""
    scheduler = _scheduler(registry)
    await scheduler.aclose()
    await scheduler.aclose()


def test_tick_report_aggregates() -> None:
    """汇总口径：派发与回收按租户求和；空租户清单为 0。"""
    report = TickReport(lock_held=True, tenants=ConcurrentStableList())
    assert report.dispatched == 0
    assert report.reclaimed == 0


async def test_tick_counts_lost_claim(
    registry: EngineRegistry, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """候选被别的实例抢先（claim 返回 False）：本实例放弃该条，不落记录不提交。"""
    await _add_task(session, next_run_at=None)

    async def _lose(*args: Any, **kwargs: Any) -> bool:
        _ = (args, kwargs)
        return False

    monkeypatch.setattr(scheduler_module, "claim_task", _lose)
    report = await _scheduler(registry).tick()
    assert report.tenants[0].claimed == 0
    assert report.dispatched == 0


async def test_tick_swallows_scan_error_inside_transaction(
    registry: EngineRegistry, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """事务内扫描抛错：本租户收敛为 0 派发（异常路径不拖垮整轮）。"""
    await _add_task(session, next_run_at=None)

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        _ = (args, kwargs)
        raise RuntimeError("scan failed")

    monkeypatch.setattr(scheduler_module, "list_due_tasks", _boom)
    report = await _scheduler(registry).tick()
    assert report.lock_held is True
    assert report.tenants[0].dispatched == 0


async def test_tick_uses_real_clock_by_default(registry: EngineRegistry, session: AsyncSession) -> None:
    """未注入时钟时取当前 UTC（naive），仍能正常派发。"""
    await _add_task(session, next_run_at=None)
    scheduler = TaskScheduler(
        settings=TaskSchedulerSettings(),
        registry=registry,
        runner=_runner(),
        lock=_StubLock(),
        tenant_keys=_keys("platform"),
        session_factory=SessionFactory(),
    )
    report = await scheduler.tick()
    assert report.dispatched == 1


async def test_run_forever_cancels_wake_task(registry: EngineRegistry) -> None:
    """长驻循环：注入唤醒信号时启动订阅协程，退出时取消并回收。"""
    from bms_core.tasks.scheduler import TaskScheduler

    class _Signal:
        async def wake_loop(self, event: asyncio.Event) -> None:
            event.set()

    settings = TaskSchedulerSettings(poll_interval_seconds=0.01)
    scheduler = TaskScheduler(
        settings=settings,
        registry=registry,
        runner=_runner(),
        lock=_StubLock(),
        tenant_keys=_keys("platform"),
        signal=cast("Any", _Signal()),
        session_factory=SessionFactory(),
        clock=lambda: NOW,
    )
    task = asyncio.create_task(scheduler.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
