"""任务调度器（beat）：逐租户扫描到期任务 → CAS 抢占 → 落记录 → 入队。

单次 `tick` 的顺序是设计的核心（《详细设计 · 任务调度》§4.3）：

1. **先取锁**（`bms:global:lock:beat`，TTL = `lock_ttl_seconds`）：取不到说明另一实例在跑，本 tick 直接跳过；
2. **逐租户扫描**（并发受 `tenant_concurrency` 限制）：`status=enabled` + `next_run_at` 到期的候选；
3. **逐条算 `next_fire` 并条件 UPDATE 抢占**：`rowcount = 1` 才算抢到——这是双 beat 不重复的唯一保障；
4. **先落 `running` 记录再入队**：反序会让执行完的消息找不到记录，且崩溃后无「执行中」痕迹；
5. **顺带回收超时 `running` 记录**：worker 失联时把记录收为 `failed`，保证「失败可查」。

锁在 `finally` 释放；tick 内**不续租**（前提是单 tick 有界：`batch_size` × `tenant_concurrency`）。
Redis 不可用（`10012` fail-closed）时**不裸跑**：抛错上抛给宿主，由宿主退避重试下一轮。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis.exceptions import RedisError

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings
from bms_core.core.exceptions import RedisUnavailableError, TaskCronInvalidError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseValueObject
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, session_scope
from bms_core.lock.base import BaseDistributedLock, build_lock_key
from bms_core.metrics.base import BaseMetrics
from bms_core.models.platform.task import TASK_TRIGGER_SCHEDULE
from bms_core.tasks.cron import next_fire, parse_cron
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.signal import TaskChangeSignal
from bms_core.tasks.spec import TaskRunSpec
from bms_core.tasks.store import (
    TaskClaim,
    claim_task,
    create_run_record,
    disable_task,
    list_due_tasks,
    reclaim_timeout_runs,
)

__all__ = ["BEAT_LOCK_RESOURCE", "TaskScheduler", "TenantTick", "TickReport"]

_LOGGER = get_logger("bms")

BEAT_LOCK_RESOURCE = "beat"
"""锁资源名（经 `build_lock_key(tenant=None, ...)` 派生 `bms:global:lock:beat`）。"""


@dataclass(frozen=True)
class TenantTick(BaseValueObject):
    """单租户一轮的结果（诊断 / 断言用）。"""

    db_key: str
    """租户库键。"""

    dispatched: int = 0
    """本轮派发条数（抢占成功且已入队）。"""

    claimed: int = 0
    """本轮抢占成功条数（含入队失败的）。"""

    reclaimed: int = 0
    """本轮回收的超时 `running` 记录数。"""

    failed: int = 0
    """入队失败条数。"""


@dataclass(frozen=True)
class TickReport(BaseValueObject):
    """一轮 tick 的汇总（诊断 / 断言用）。"""

    lock_held: bool
    """是否取到调度锁；False 表示本 tick 被跳过。"""

    tenants: ConcurrentStableList[TenantTick]
    """各租户结果。"""

    @property
    def dispatched(self) -> int:
        """本轮派发总数。

        Returns:
            int: 派发条数。
        """
        return sum(item.dispatched for item in self.tenants)

    @property
    def reclaimed(self) -> int:
        """本轮回收总数。

        Returns:
            int: 回收条数。
        """
        return sum(item.reclaimed for item in self.tenants)


class TaskScheduler(BaseAsyncResource):
    """单副本调度器（长驻由 `ops/task_scheduler.py --beat` 承载）。"""

    def __init__(
        self,
        *,
        settings: TaskSchedulerSettings,
        registry: EngineRegistry,
        queue: TaskQueue,
        lock: BaseDistributedLock,
        tenant_keys: Callable[[], Awaitable[ConcurrentStableList[str]]],
        signal: TaskChangeSignal | None = None,
        session_factory: SessionFactory | None = None,
        metrics: BaseMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """初始化。

        Args:
            settings: 调度参数。
            registry: 引擎注册表（按租户库键开会话）。
            queue: 待执行队列。
            lock: 分布式锁（单副本互斥）。
            tenant_keys: 租户库键提供者（带缓存的枚举入口）。
            signal: 变更信号（None 表示不订阅，只按周期轮询）。
            session_factory: 会话工厂（测试注入）。
            metrics: 指标记录器（None 表示不记录）。
            clock: 时钟（naive UTC；测试注入固定时刻）。
        """
        self._settings = settings
        self._registry = registry
        self._queue = queue
        self._lock = lock
        self._tenant_keys = tenant_keys
        self._signal = signal
        self._session_factory = session_factory
        self._metrics = metrics
        self._clock = clock if clock is not None else _utc_now_naive

    @property
    def lock_key(self) -> str:
        """调度锁 key。

        Returns:
            str: 锁 key（`bms:global:lock:beat`）。
        """
        return build_lock_key(tenant=None, resource=BEAT_LOCK_RESOURCE)

    async def aclose(self) -> None:
        """释放资源（本类不持有长连接；保留钩子以满足资源基类契约）。"""

    async def run_forever(self) -> None:
        """长驻循环：tick 一次，然后等「变更信号唤醒」或「周期到点」。

        Raises:
            RedisUnavailableError: 锁不可用（fail-closed，不裸跑）；由宿主退避后重试。
        """
        wake = asyncio.Event()
        wake_task: asyncio.Task[None] | None = None
        if self._signal is not None:
            wake_task = asyncio.create_task(self._signal.wake_loop(wake))
        try:
            while True:
                await self.tick()
                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=self._settings.poll_interval_seconds)
                except TimeoutError:
                    continue
        finally:
            if wake_task is not None:
                wake_task.cancel()
                await asyncio.gather(wake_task, return_exceptions=True)

    async def tick(self) -> TickReport:
        """执行一轮调度（取锁 → 逐租户抢派 → 回收超时）。

        Returns:
            TickReport: 本轮汇总；未取到锁时 `lock_held=False`。

        Raises:
            RedisUnavailableError: 锁不可用（`10012`）；调用方退避重试，不得降级裸跑。
        """
        token = await self._lock.acquire(self.lock_key, ttl=self._settings.lock_ttl_seconds)
        if token is None:
            return TickReport(lock_held=False, tenants=ConcurrentStableList())
        try:
            keys = await self._tenant_keys()
            semaphore = asyncio.Semaphore(self._settings.tenant_concurrency)
            results = await asyncio.gather(*(self._tick_tenant(key, semaphore) for key in keys))
        finally:
            await self._lock.release(self.lock_key, token)
        return TickReport(lock_held=True, tenants=ConcurrentStableList(results))

    async def _tick_tenant(self, db_key: str, semaphore: asyncio.Semaphore) -> TenantTick:
        """处理单个租户库（扫描 → 抢占 → 落记录 → 入队 → 回收）。

        Args:
            db_key: 租户库键。
            semaphore: 并发闸门。

        Returns:
            TenantTick: 本租户结果。
        """
        moment = self._clock()
        specs: ConcurrentStableList[TaskRunSpec] = ConcurrentStableList()
        claimed = 0
        reclaimed = 0
        async with semaphore:
            try:
                async with (
                    session_scope(self._registry, db_key=db_key, factory=self._session_factory) as session,
                    session.begin(),
                ):
                    reclaimed = await reclaim_timeout_runs(
                        session,
                        cutoff=moment - timedelta(seconds=self._settings.run_timeout_seconds),
                        finished_at=moment,
                    )
                    claims = await list_due_tasks(session, now=moment, limit=self._settings.batch_size)
                    for claim in claims:
                        spec = await self._claim_one(session, db_key, claim, moment)
                        if spec is not None:
                            claimed += 1
                            specs.append(spec)
            except Exception as exc:  # 单租户失败不拖垮其他租户
                _LOGGER.error("任务调度扫描租户失败（其他租户继续）", db_key=db_key, error=str(exc))
                return TenantTick(db_key=db_key, reclaimed=reclaimed)
        dispatched = 0
        failed = 0
        for spec in specs:
            if await self._enqueue(spec):
                dispatched += 1
            else:
                failed += 1
        if self._metrics is not None:
            await self._metrics.counter(
                "bms_task_dispatch_total", value=float(dispatched), labels={"source": "schedule"}
            )
        return TenantTick(db_key=db_key, dispatched=dispatched, claimed=claimed, reclaimed=reclaimed, failed=failed)

    async def _claim_one(
        self,
        session: DbSession,
        db_key: str,
        claim: TaskClaim,
        moment: datetime,
    ) -> TaskRunSpec | None:
        """算下次到期并抢占一条任务；抢到则落 `running` 记录并返回待入队规格。

        Args:
            session: 租户库会话。
            db_key: 租户库键（写进队列载荷，执行器据此取库会话）。
            claim: 到期候选。
            moment: 当前时刻（naive UTC）。

        Returns:
            TaskRunSpec | None: 抢到返回规格；未抢到 / cron 无法计算返回 None。
        """
        try:
            upcoming = next_fire(parse_cron(claim.cron), moment.replace(tzinfo=UTC))
        except TaskCronInvalidError as exc:
            _LOGGER.error("任务 cron 无法计算，自动停用", task_id=claim.task_id, cron=claim.cron, error=str(exc))
            await disable_task(session, task_id=claim.task_id, now=moment)
            return None
        if not await claim_task(
            session,
            task_id=claim.task_id,
            next_run_at=upcoming.replace(tzinfo=None),
            now=moment,
        ):
            return None
        run_id = uuid4().hex
        log_id = await create_run_record(
            session,
            task_id=claim.task_id,
            run_id=run_id,
            trigger_source=TASK_TRIGGER_SCHEDULE,
            started_at=moment,
        )
        return TaskRunSpec(
            db_key=db_key,
            task_id=claim.task_id,
            log_id=log_id,
            run_id=run_id,
            code=claim.code,
            handler=claim.handler,
            args_json=claim.args_json,
        )

    async def _enqueue(self, spec: TaskRunSpec) -> bool:
        """入队一条已落记录的运行规格。

        Args:
            spec: 运行规格（`db_key` 已在调用处补齐）。

        Returns:
            bool: 入队成功 True；Redis 不可用 False（记录留待超时回收）。
        """
        try:
            await self._queue.push(spec)
        except (RedisUnavailableError, RedisError) as exc:
            _LOGGER.error("任务入队失败（记录留待超时回收）", task_id=spec.task_id, run_id=spec.run_id, error=str(exc))
            return False
        return True


def _utc_now_naive() -> datetime:
    """当前 UTC 时间（naive，与表列同形）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)
