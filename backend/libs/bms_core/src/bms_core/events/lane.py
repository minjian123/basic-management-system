"""键级串行执行器：同键必落同道、道内严格串行、道间并发。

用途：事件消费组内保证「同一聚合 / 同一租户的事件按拉取顺序处理」。

- **为什么需要**：Python gRPC 客户端不提供 Java 那样的 FIFO topic 语义，而审计链组要求
  「分区键 = 租户」串行追加（`prev_hash` 衔接）。仅靠「不 ack 就不重投」不能防并发乱序。
- **怎么做**：按 key 哈希到固定道数（`lanes`），每道一条队列 + 一个 worker 协程；同 key 恒落同道
  → 同键任务严格串行；不同键分散到不同道 → 保留并发。
- **有序组**：默认全组串行（`lanes = 1`）；动态模式下按**链键**精确建道（同键串行、跨键并行），
  活跃键数超 `limit` 时新键按稳定哈希合并到桶道，空闲道按 `idle_seconds` 回收。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections.abc import Awaitable, Callable

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import EventConsumeError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject

__all__ = ["KeyedLaneExecutor", "lane_index"]

_LaneQueue = asyncio.Queue[tuple[asyncio.Future[object], Callable[[], Awaitable[object]]]]
"""单道队列元素：结果回填句柄 + 任务工厂。"""

_LOGGER = get_logger("bms")


def lane_index(key: str, lanes: int) -> int:
    """按键计算所属道号（稳定哈希，跨进程一致）。

    Args:
        key: 分区键（`aggregate_key` / `tenant_id` / `event_id`）。
        lanes: 道数（≥1）。

    Returns:
        int: 道号（0 ~ lanes-1）。

    Raises:
        EventConsumeError: 道数非法。
    """
    if lanes < 1:
        raise EventConsumeError(f"键级执行器道数非法（应 ≥1）：{lanes}")
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=2).digest()
    return int.from_bytes(digest, "big") % lanes


class KeyedLaneExecutor(BaseFrameworkObject):
    """键级串行执行器（懒启动 worker；`aclose` 排水后取消）。"""

    def __init__(
        self,
        lanes: int = 1,
        *,
        dynamic: bool = False,
        limit: int = 64,
        idle_seconds: float = 600.0,
    ) -> None:
        """初始化。

        Args:
            lanes: 固定道数（1 = 全串行；有序组动态模式不使用）。
            dynamic: True = 按链键动态建道（精确键；超上限按稳定哈希合并到桶道）。
            limit: 动态模式活跃道上限（≥1）。
            idle_seconds: 动态模式道空闲回收阈值（秒；>0）。

        Raises:
            EventConsumeError: 道数 / 上限 / 回收阈值非法。
        """
        if lanes < 1:
            raise EventConsumeError(f"键级执行器道数非法（应 ≥1）：{lanes}")
        if limit < 1:
            raise EventConsumeError(f"键级执行器道上限非法（应 ≥1）：{limit}")
        if idle_seconds <= 0:
            raise EventConsumeError(f"键级执行器空闲回收阈值非法（应 >0）：{idle_seconds}")
        self._lanes = lanes
        self._dynamic = dynamic
        self._limit = limit
        self._idle_seconds = idle_seconds
        self._queues: ConcurrentStableList[_LaneQueue] = ConcurrentStableList(asyncio.Queue() for _ in range(lanes))
        self._workers: ConcurrentStableList[asyncio.Task[None]] = ConcurrentStableList()
        self._key_lane: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        """链键 → 道名（动态模式；道回收后映射保留，重建时复用同名道）。"""
        self._dynamic_queues: ConcurrentStableDict[str, _LaneQueue] = ConcurrentStableDict()
        self._dynamic_workers: ConcurrentStableDict[str, asyncio.Task[None]] = ConcurrentStableDict()
        self._dynamic_active: ConcurrentStableDict[str, float] = ConcurrentStableDict()
        self._dynamic_busy: ConcurrentStableDict[str, bool] = ConcurrentStableDict()
        self._last_reap = 0.0
        self._closed = False

    @property
    def lanes(self) -> int:
        """道数（动态模式为当前活跃道数）。

        Returns:
            int: 道数。
        """
        return len(self._dynamic_queues) if self._dynamic else self._lanes

    async def submit[T](self, key: str, job: Callable[[], Awaitable[T]]) -> T:
        """提交一个任务并等待结果（同键任务按提交顺序串行执行）。

        Args:
            key: 分区键 / 链键。
            job: 任务（协程工厂，调用即执行）。

        Returns:
            T: 任务返回值。

        Raises:
            EventConsumeError: 执行器已关闭，或任务抛错（异常原样透传）。
        """
        if self._closed:
            raise EventConsumeError("键级执行器已关闭，拒绝新任务")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[object] = loop.create_future()
        # 类型擦除转交：worker 侧按 object 处理，异常经 future 原样回传
        cast_job: Callable[[], Awaitable[object]] = job  # pyright: ignore[reportAssignmentType]
        if self._dynamic:
            queue = await self._dynamic_lane(key)
            queue.put_nowait((future, cast_job))
        else:
            index = lane_index(key, self._lanes)
            self._ensure_worker(index)
            self._queues[index].put_nowait((future, cast_job))
        return await future  # pyright: ignore[reportReturnType]

    async def join(self) -> None:
        """等待所有已入队任务执行完毕（不关闭执行器）。"""
        if self._dynamic:
            for queue in self._dynamic_queues.values():
                await queue.join()
            return
        for queue in self._queues:
            await queue.join()

    async def aclose(self) -> None:
        """关闭执行器：等已入队任务跑完再取消 worker（幂等）。"""
        if self._closed:
            return
        self._closed = True
        if self._dynamic:
            for queue in self._dynamic_queues.values():
                await queue.join()
            for worker in self._dynamic_workers.values():
                worker.cancel()
            for worker in self._dynamic_workers.values():
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
            self._dynamic_workers.clear()
            self._dynamic_queues.clear()
            self._dynamic_active.clear()
            return
        for queue in self._queues:
            await queue.join()
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()

    async def reap_idle(self, *, now: float | None = None) -> int:
        """回收空闲道（动态模式；返回回收道数）。

        Args:
            now: 当前时刻（测试可注入；None 取 `time.monotonic()`）。

        Returns:
            int: 本次回收的道数。
        """
        if not self._dynamic:
            return 0
        moment = time.monotonic() if now is None else now
        self._last_reap = moment
        expired: ConcurrentStableList[str] = ConcurrentStableList()
        for name, active_at in self._dynamic_active.items():
            if moment - active_at >= self._idle_seconds:
                expired.add(name)
        reaped = 0
        for name in expired:
            queue = self._dynamic_queues.get(name)
            if queue is not None and not queue.empty():
                continue
            if self._dynamic_busy.get(name, False):
                continue
            worker = self._dynamic_workers.pop(name, None)
            if worker is not None:
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
            self._dynamic_queues.pop(name, None)
            self._dynamic_active.pop(name, None)
            self._dynamic_busy.pop(name, None)
            reaped += 1
        return reaped

    def _ensure_worker(self, index: int) -> None:
        """按需启动某道的 worker（固定道模式）。

        Args:
            index: 道号。
        """
        while len(self._workers) <= index:
            self._workers.add(asyncio.create_task(self._run(len(self._workers))))

    async def _dynamic_lane(self, key: str) -> _LaneQueue:
        """取（或创建）链键对应道（动态模式）。

        Args:
            key: 链键。

        Returns:
            _LaneQueue: 该道的队列。
        """
        name = self._key_lane.get(key)
        if name is None:
            name = self._pick_lane(key)
            self._key_lane.set(key, name)
        if name not in self._dynamic_queues and len(self._dynamic_queues) >= self._limit:
            # 已建道达到上限：改投既有道（同键映射同步更新），保证适用范围内总道数不超限。
            name = self._pick_lane(key)
            self._key_lane.set(key, name)
        queue: _LaneQueue | None = self._dynamic_queues.get(name)
        if queue is None:
            created: _LaneQueue = asyncio.Queue()
            self._dynamic_queues.set(name, created)
            self._dynamic_workers.set(name, asyncio.create_task(self._run_dynamic(name)))
            queue = created
        self._dynamic_active.set(name, time.monotonic())
        now = time.monotonic()
        if now - self._last_reap >= self._idle_seconds / 2:
            await self.reap_idle(now=now)
        return queue

    def _pick_lane(self, key: str) -> str:
        """为链键选道名（未超上限用键本身，超上限按稳定哈希复用既有道）。

        Args:
            key: 链键。

        Returns:
            str: 道名。
        """
        if len(self._dynamic_queues) < self._limit:
            return key
        names = ConcurrentStableList(sorted(self._dynamic_queues.keys()))
        return names[lane_index(key, len(names))] if names else key

    async def _run(self, index: int) -> None:
        """单道 worker 循环（取消时退出）。

        Args:
            index: 道号。
        """
        await self._drain(self._queues[index], f"fixed:{index}")

    async def _run_dynamic(self, name: str) -> None:
        """动态道 worker 循环（取消时退出）。

        Args:
            name: 道名（链键或桶道）。
        """
        queue = self._dynamic_queues.get(name)
        if queue is None:  # pragma: no cover - 回收与重建竞态（队列刚被移除）
            return
        await self._drain(
            queue,
            name,
            on_start=lambda: self._dynamic_busy.set(name, True),
            on_done=lambda: self._mark_dynamic_idle(name),
        )

    def _mark_dynamic_idle(self, name: str) -> None:
        """标记道空闲并刷新活跃时刻（回收判定用）。

        Args:
            name: 道名。
        """
        self._dynamic_busy.set(name, False)
        self._dynamic_active.set(name, time.monotonic())

    async def _drain(
        self,
        queue: _LaneQueue,
        label: str,
        *,
        on_start: Callable[[], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        """从队列取任务执行并回填结果（异常回传给提交方，不终止该道）。

        Args:
            queue: 道队列。
            label: 日志用道标识。
            on_start: 任务开始前的钩子（动态道标记忙）。
            on_done: 任务结束后的钩子（动态道标记空闲并刷新活跃时刻）。
        """
        while True:
            future, job = await queue.get()
            try:
                if future.cancelled():  # pragma: no cover - 提交方取消后的竞态
                    continue
                if on_start is not None:
                    on_start()
                try:
                    result = await job()
                except asyncio.CancelledError:  # pragma: no cover - 关闭期取消传播
                    raise
                except Exception as exc:  # 任务异常回传给提交方，不终止该道
                    if not future.done():  # pragma: no cover - 提交方已取消的竞态
                        future.set_exception(exc)
                    _LOGGER.debug("event_lane_job_failed", lane=label, error=repr(exc))
                else:
                    if not future.done():  # pragma: no cover - 提交方已取消的竞态
                        future.set_result(result)
            finally:
                if on_done is not None:
                    on_done()
                queue.task_done()
