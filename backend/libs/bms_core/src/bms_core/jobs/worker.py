"""每服务作业消费者（worker）：轮询 / 条件抢占 / 并发公平 / 执行 / 停机。

- **每服务独立进程**：`bms_<service>.jobs` 构造本 worker；库范围由宿主提供（平台服务扫平台链 + 租户链，
  产品服务只扫自身平台库 + 租户库），跨服务作业不互相扫描；
- **抢占靠数据库条件 UPDATE**：多副本 / 租约回收同时发生时只有一个 worker 抢到；
- **公平**：全局并发 + 单租户并发上限 + 类型并发上限，priority 只在同租户内排序；
- **优雅停机**：停止抢占，等在途作业到批次边界结束；未完成作业保留租约，到期由其他 worker 回收。
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import JobHandlerNotRegisteredError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, session_scope
from bms_core.jobs import store
from bms_core.jobs.events import enqueue_job_event, started_envelope
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobExecutor
from bms_core.jobs.signal import JobChangeSignal
from bms_core.jobs.spec import JobSnapshot, JobTypeSpec, now_utc
from bms_core.jobs.store import snapshot_of
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import BaseOutboxStore

__all__ = ["JobTickReport", "JobWorker"]

_LOGGER = get_logger("bms")

DbKeyProvider = Callable[[], Awaitable[ConcurrentStableList[str]]]
"""库键提供者（带缓存；平台服务返回两条链，产品服务返回自身两条链）。"""


class JobTickReport(BaseFrameworkObject):
    """一轮 tick 汇总（诊断 / 断言用）。"""

    def __init__(self, *, claimed: int = 0, executed: int = 0, requeued: int = 0, dead: int = 0) -> None:
        """初始化。

        Args:
            claimed: 本轮抢占条数。
            executed: 本轮执行完成条数。
            requeued: 本轮租约回收回队条数。
            dead: 本轮转死信条数（含超限与回收）。
        """
        self.claimed = claimed
        self.executed = executed
        self.requeued = requeued
        self.dead = dead


class JobWorker(BaseFrameworkObject):
    """单服务作业消费者（长驻由 `bms_<service>.jobs` 承载）。"""

    def __init__(
        self,
        *,
        service_key: str,
        registry: JobHandlerRegistry,
        specs: dict[str, JobTypeSpec],
        limits: JobLimits,
        engine_registry: EngineRegistry,
        db_keys: DbKeyProvider,
        session_factory: SessionFactory | None = None,
        outbox: BaseOutboxStore | None = None,
        signal: JobChangeSignal | None = None,
        metrics: BaseMetrics | None = None,
        worker_id: str | None = None,
        clock: Callable[[], Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """初始化。

        Args:
            service_key: 本服务标识（作业只在本服务声明的类型内抢占）。
            registry: 本服务 handler 注册表。
            specs: 本服务作业类型声明。
            limits: 作业生效参数。
            engine_registry: 引擎注册表（按库键开会话）。
            db_keys: 库键提供者（带缓存）。
            session_factory: 会话工厂（测试注入）。
            outbox: 发件箱存储。
            signal: 唤醒信号（None 表示只按周期轮询）。
            metrics: 指标记录器（None 表示不记录）。
            worker_id: 执行者实例标识（缺省 `{service}-{hostname}-{pid}`）。
            clock: 时钟（测试注入）。
            sleep: 睡眠（测试注入）。
        """
        self._service_key = service_key
        self._registry = registry
        self._specs = specs
        self._limits = limits
        self._engine_registry = engine_registry
        self._db_keys = db_keys
        self._session_factory = session_factory
        self._outbox = outbox
        self._signal = signal
        self._metrics = metrics
        self._worker_id = worker_id or f"{service_key}-{socket.gethostname()}-{os.getpid()}"
        self._clock = clock if clock is not None else now_utc
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._stopping = asyncio.Event()
        self._global_semaphore = asyncio.Semaphore(limits.global_concurrency)
        self._tenant_semaphores: ConcurrentStableDict[str, asyncio.Semaphore] = ConcurrentStableDict()
        self._type_semaphores: ConcurrentStableDict[str, asyncio.Semaphore] = ConcurrentStableDict()
        self._inflight: ConcurrentStableList[asyncio.Task[None]] = ConcurrentStableList()
        missing = [job_type for job_type in specs if not registry.has(job_type)]
        if missing:
            raise JobHandlerNotRegisteredError(f"作业类型声明存在但代码侧 handler 缺失：{sorted(missing)}")

    @property
    def worker_id(self) -> str:
        """执行者实例标识。

        Returns:
            str: worker 标识。
        """
        return self._worker_id

    @property
    def stopping(self) -> bool:
        """是否已置停止标志。

        Returns:
            bool: 已停止 True。
        """
        return self._stopping.is_set()

    async def aclose(self) -> None:
        """优雅停机：停止抢占，等待在途作业完成（超时则留待租约回收）。"""
        self._stopping.set()
        tasks = list(self._inflight)
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=self._limits.shutdown_grace_seconds
            )
        except TimeoutError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._inflight = ConcurrentStableList()

    async def run_forever(self) -> None:
        """长驻循环：tick 一次，然后等唤醒信号或周期到点。"""
        self._stopping.clear()
        wake = asyncio.Event()
        wake_task: asyncio.Task[None] | None = None
        if self._signal is not None:
            wake_task = asyncio.create_task(self._signal.wake_loop(wake))
        try:
            while not self._stopping.is_set():
                await self.tick()
                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=self._limits.poll_interval_seconds)
                except TimeoutError:
                    continue
        finally:
            if wake_task is not None:
                wake_task.cancel()
                await asyncio.gather(wake_task, return_exceptions=True)

    async def run_once(self) -> JobTickReport:
        """跑一轮 tick 即返回（诊断 / 冒烟）。

        Returns:
            JobTickReport: 本轮汇总。
        """
        return await self.tick()

    async def tick(self) -> JobTickReport:
        """扫描各库：回收租约 → 抢占 → 并发执行。

        Returns:
            JobTickReport: 本轮汇总。
        """
        if self._stopping.is_set():
            return JobTickReport()
        keys = await self._db_keys()
        snapshots: ConcurrentStableList[JobSnapshot] = ConcurrentStableList()
        requeued = 0
        dead = 0
        for db_key in keys:
            try:
                round_snapshots, round_requeued, round_dead = await self._claim_round(db_key)
            except Exception as exc:  # 单库失败不拖垮其他库
                _LOGGER.error("作业抢占扫描失败（其他库继续）", db_key=db_key, error=str(exc))
                continue
            snapshots.extend(round_snapshots)
            requeued += round_requeued
            dead += round_dead
        executed = 0
        if snapshots:
            results = await asyncio.gather(*(self._execute_one(item) for item in snapshots))
            executed = sum(1 for item in results if item)
        return JobTickReport(claimed=len(snapshots), executed=executed, requeued=requeued, dead=dead)

    async def _claim_round(self, db_key: str) -> tuple[ConcurrentStableList[JobSnapshot], int, int]:
        """单库一轮：回收租约 → 取候选 → 条件抢占。

        Args:
            db_key: 库键。

        Returns:
            tuple[ConcurrentStableList[JobSnapshot], int, int]: （已抢占快照, 回收回队数, 死信数）。
        """
        now = self._clock()
        snapshots: ConcurrentStableList[JobSnapshot] = ConcurrentStableList()
        requeued = 0
        dead = 0
        async with self._tx(db_key) as session, session.begin():
            reclaim = await store.reclaim_expired(session, now=now)
            requeued += reclaim.requeued
            dead += reclaim.dead
            claims = await store.claim_candidates(
                session, now=now, limit=self._limits.claim_batch_size, job_types=self._job_types()
            )
            for claim in claims:
                if claim.attempts + 1 > claim.max_attempts:
                    if await store.mark_dead(
                        session, job_id=claim.job_id, error_text="执行次数已达上限（抢占前判定）", now=now
                    ):
                        dead += 1
                    continue
                claimed = await store.claim_job(
                    session,
                    job_id=claim.job_id,
                    worker_id=self._worker_id,
                    lease_until=now + timedelta(seconds=self._limits.lease_seconds),
                    now=now,
                )
                if not claimed:
                    continue
                record = await store.get_job(session, claim.job_id)
                if record is None:
                    continue
                snapshots.add(_with_runtime(snapshot_of(record), db_key=db_key, worker_id=self._worker_id))
                await enqueue_job_event(
                    session,
                    started_envelope(
                        job_id=int(record.id),
                        job_type=record.job_type,
                        service_key=record.service_key,
                        attempt=int(record.attempts),
                    ),
                    outbox=self._outbox,
                )
        if self._metrics is not None:
            await self._metrics.counter("bms_job_claimed_total", value=float(len(snapshots)))
        return snapshots, requeued, dead

    async def _execute_one(self, snapshot: JobSnapshot) -> bool:
        """受全局 / 租户 / 类型三重并发约束执行一条作业。

        Args:
            snapshot: 作业快照。

        Returns:
            bool: 执行完成 True；并发等待期间停机 False。
        """
        tenant_key = "" if snapshot.tenant_id is None else str(snapshot.tenant_id)
        tenant_semaphore = self._tenant_semaphores.get(tenant_key)
        if tenant_semaphore is None:
            tenant_semaphore = asyncio.Semaphore(self._limits.per_tenant_concurrency)
            self._tenant_semaphores.set(tenant_key, tenant_semaphore)
        spec = self._specs.get(snapshot.job_type)
        type_semaphore = self._type_semaphores.get(snapshot.job_type)
        if type_semaphore is None:
            type_semaphore = asyncio.Semaphore(spec.concurrency if spec is not None else 1)
            self._type_semaphores.set(snapshot.job_type, type_semaphore)
        async with self._global_semaphore, tenant_semaphore, type_semaphore:
            if self._stopping.is_set():
                return False
            task = asyncio.create_task(self._run_one(snapshot, spec))
            self._inflight.add(task)
            try:
                await task
            finally:
                if task in self._inflight:
                    self._inflight.remove(task)
            return True

    async def _run_one(self, snapshot: JobSnapshot, spec: JobTypeSpec | None) -> None:
        """执行一条作业（终态由 `JobExecutor` 收敛）。

        Args:
            snapshot: 作业快照。
            spec: 类型声明（缺失时用默认参数）。
        """
        handler = self._registry.get(snapshot.job_type)
        executor = JobExecutor(
            limits=self._limits,
            session_provider=lambda: self._tx(snapshot.db_key),
            worker_id=self._worker_id,
            outbox=self._outbox,
            heartbeat_enabled=True,
            clock=self._clock,
            sleep=self._sleep,
        )
        started = asyncio.get_running_loop().time()
        result = await executor.execute(
            handler,
            snapshot,
            timeout_seconds=spec.timeout_seconds if spec is not None else self._limits.timeout_seconds_default,
            backoff_seconds=spec.backoff_seconds if spec is not None else self._limits.backoff_seconds_default,
        )
        if self._metrics is not None:
            await self._metrics.counter(
                "bms_job_run_total", value=1.0, labels={"job_type": snapshot.job_type, "status": result.status}
            )
            await self._metrics.histogram(
                "bms_job_run_seconds",
                value=asyncio.get_running_loop().time() - started,
                labels={"job_type": snapshot.job_type},
            )
        if result.status == "failed":
            _LOGGER.warning("作业执行失败", job_id=snapshot.id, job_type=snapshot.job_type, message=result.message)

    def _job_types(self) -> ConcurrentStableList[str]:
        """本服务声明的作业类型清单。

        Returns:
            ConcurrentStableList[str]: 作业类型清单。
        """
        return ConcurrentStableList(self._specs.keys())

    @asynccontextmanager
    async def _tx(self, db_key: str) -> AsyncGenerator[DbSession]:
        """打开一个会话（事务边界由调用方 / 作业写操作自行管理）。

        Args:
            db_key: 库键。

        Yields:
            DbSession: 会话。
        """
        async with session_scope(self._engine_registry, db_key=db_key, factory=self._session_factory) as session:
            yield session


def _with_runtime(snapshot: JobSnapshot, *, db_key: str, worker_id: str) -> JobSnapshot:
    """补齐快照运行期字段。

    Args:
        snapshot: 原始快照。
        db_key: 库键。
        worker_id: 执行者标识。

    Returns:
        JobSnapshot: 补齐后的快照。
    """
    return replace(snapshot, db_key=db_key, lease_owner=worker_id)
