"""键级串行执行器护栏：同键串行 / 跨键并发 / 异常透传 / 关闭排水。

依据《详细设计 · 事件总线》§4.4：同 `aggregate_key`（或租户）的事件必须严格按拉取顺序处理，
不同键之间允许并发——这是 Python gRPC 客户端无 FIFO 语义下保证审计链顺序的唯一可靠做法。
"""

import asyncio

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import EventConsumeError
from bms_core.events.lane import KeyedLaneExecutor, lane_index


def test_lane_index_is_stable_and_bounded() -> None:
    """同键恒定落同道；道号在 [0, lanes) 内；不同键可分散。"""
    assert lane_index("tenant-1", 4) == lane_index("tenant-1", 4)
    assert 0 <= lane_index("tenant-1", 4) < 4
    assert lane_index("tenant-1", 1) == 0


def test_lane_index_rejects_bad_lanes() -> None:
    """道数非法即拒（0 / 负数）。"""
    with pytest.raises(EventConsumeError):
        lane_index("k", 0)


async def test_same_key_runs_serially() -> None:
    """同键任务严格串行：后一个任务在前一个完成前不会开始。"""
    executor = KeyedLaneExecutor(lanes=4)
    order: ConcurrentStableList[str] = ConcurrentStableList()
    running = 0
    max_running = 0

    async def job(name: str) -> str:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        order.add(f"start:{name}")
        await asyncio.sleep(0.01)
        order.add(f"end:{name}")
        running -= 1
        return name

    results = await asyncio.gather(
        executor.submit("tenant-1", lambda: job("a")),
        executor.submit("tenant-1", lambda: job("b")),
        executor.submit("tenant-1", lambda: job("c")),
    )
    await executor.aclose()

    assert list(results) == ["a", "b", "c"]
    assert max_running == 1
    assert list(order) == ["start:a", "end:a", "start:b", "end:b", "start:c", "end:c"]


async def test_different_keys_run_concurrently() -> None:
    """不同键（落不同道）可并行：用屏障证明两者同时在跑。"""
    executor = KeyedLaneExecutor(lanes=2)
    both_running = asyncio.Event()
    started = 0

    async def job() -> None:
        nonlocal started
        started += 1
        if started == 2:
            both_running.set()
        await asyncio.wait_for(both_running.wait(), timeout=1.0)

    # 选两个落不同道的键（道数 2 时必有一对不同道）
    keys = [f"tenant-{index}" for index in range(20)]
    pair = next(
        (a, b) for index, a in enumerate(keys) for b in keys[index + 1 :] if lane_index(a, 2) != lane_index(b, 2)
    )
    await asyncio.gather(executor.submit(pair[0], job), executor.submit(pair[1], job))
    await executor.aclose()
    assert both_running.is_set()


async def test_job_exception_propagates() -> None:
    """任务异常回传给提交方，且不终止该道后续任务。"""
    executor = KeyedLaneExecutor(lanes=1)

    async def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await executor.submit("k", boom)
    assert await executor.submit("k", lambda: _ok()) == "ok"
    await executor.aclose()


async def _ok() -> str:
    """成功任务。

    Returns:
        str: 固定返回值。
    """
    return "ok"


async def test_close_drains_pending_jobs() -> None:
    """关闭前已入队任务会跑完（不丢在途）。"""
    executor = KeyedLaneExecutor(lanes=1)
    done: ConcurrentStableList[int] = ConcurrentStableList()

    async def job(value: int) -> None:
        await asyncio.sleep(0.01)
        done.add(value)

    futures = [asyncio.create_task(executor.submit("k", lambda value=value: job(value))) for value in range(3)]
    await asyncio.sleep(0)
    await executor.aclose()
    await asyncio.gather(*futures)
    assert sorted(done) == [0, 1, 2]


async def test_submit_after_close_rejected() -> None:
    """关闭后拒绝新任务。"""
    executor = KeyedLaneExecutor(lanes=1)
    await executor.aclose()

    async def job() -> None:
        return None

    with pytest.raises(EventConsumeError, match="已关闭"):
        await executor.submit("k", job)


async def test_close_is_idempotent() -> None:
    """关闭可重复调用。"""
    executor = KeyedLaneExecutor(lanes=2)
    await executor.aclose()
    await executor.aclose()


def test_constructor_rejects_bad_lanes() -> None:
    """构造期校验道数。"""
    with pytest.raises(EventConsumeError):
        KeyedLaneExecutor(lanes=0)
