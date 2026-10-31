"""键级串行执行器：同键必落同道、道内严格串行、道间并发。

用途：事件消费组内保证「同一聚合 / 同一租户的事件按拉取顺序处理」。

- **为什么需要**：Python gRPC 客户端不提供 Java 那样的 FIFO topic 语义，而审计链组要求
  「分区键 = 租户」串行追加（`prev_hash` 衔接）。仅靠「不 ack 就不重投」不能防并发乱序。
- **怎么做**：按 key 哈希到固定道数（`lanes`），每道一条队列 + 一个 worker 协程；同 key 恒落同道
  → 同键任务严格串行；不同键分散到不同道 → 保留并发。
- **有序组**：`lanes = 1` 即全组串行（审计链组），语义与「单线程消费」等价但复用同一实现。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections.abc import Awaitable, Callable

from bms_core.core.concurrent import ConcurrentStableList
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

    def __init__(self, lanes: int = 1) -> None:
        """初始化。

        Args:
            lanes: 道数（1 = 全串行；有序组固定 1）。

        Raises:
            EventConsumeError: 道数非法。
        """
        if lanes < 1:
            raise EventConsumeError(f"键级执行器道数非法（应 ≥1）：{lanes}")
        self._lanes = lanes
        self._queues: ConcurrentStableList[_LaneQueue] = ConcurrentStableList(asyncio.Queue() for _ in range(lanes))
        self._workers: ConcurrentStableList[asyncio.Task[None]] = ConcurrentStableList()
        self._closed = False

    @property
    def lanes(self) -> int:
        """道数。

        Returns:
            int: 道数。
        """
        return self._lanes

    async def submit[T](self, key: str, job: Callable[[], Awaitable[T]]) -> T:
        """提交一个任务并等待结果（同键任务按提交顺序串行执行）。

        Args:
            key: 分区键。
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
        self._ensure_worker(lane_index(key, self._lanes))
        # 类型擦除转交：worker 侧按 object 处理，异常经 future 原样回传
        cast_job: Callable[[], Awaitable[object]] = job  # pyright: ignore[reportAssignmentType]
        self._queues[lane_index(key, self._lanes)].put_nowait((future, cast_job))
        return await future  # pyright: ignore[reportReturnType]

    async def join(self) -> None:
        """等待所有已入队任务执行完毕（不关闭执行器）。"""
        for queue in self._queues:
            await queue.join()

    async def aclose(self) -> None:
        """关闭执行器：等已入队任务跑完再取消 worker（幂等）。"""
        if self._closed:
            return
        self._closed = True
        for queue in self._queues:
            await queue.join()
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._workers.clear()

    def _ensure_worker(self, index: int) -> None:
        """按需启动某道的 worker。

        Args:
            index: 道号。
        """
        while len(self._workers) <= index:
            self._workers.add(asyncio.create_task(self._run(len(self._workers))))

    async def _run(self, index: int) -> None:
        """单道 worker 循环（取消时退出）。

        Args:
            index: 道号。
        """
        queue = self._queues[index]
        while True:
            future, job = await queue.get()
            try:
                if future.cancelled():  # pragma: no cover - 提交方取消后的竞态
                    continue
                try:
                    result = await job()
                except asyncio.CancelledError:  # pragma: no cover - 关闭期取消传播
                    raise
                except Exception as exc:  # 任务异常回传给提交方，不终止该道
                    if not future.done():  # pragma: no cover - 提交方已取消的竞态
                        future.set_exception(exc)
                    _LOGGER.debug("event_lane_job_failed", lane=index, error=repr(exc))
                else:
                    if not future.done():  # pragma: no cover - 提交方已取消的竞态
                        future.set_result(result)
            finally:
                queue.task_done()
