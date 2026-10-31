"""执行器护栏：成功 / 重试与耗尽 / 跳过 / 未登记 handler / 参数非法 / 脏消息 / 取消回队 / 终态事件。"""

import asyncio
from datetime import datetime
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.metrics.null import NullMetrics
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.task import (
    TASK_RUN_FAILED,
    TASK_RUN_RUNNING,
    TASK_RUN_SKIPPED,
    TASK_RUN_SUCCESS,
    SysTask,
    SysTaskLog,
)
from bms_core.outbox.store import SqlOutboxStore
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.spec import TaskContext, TaskResult, TaskRunSpec
from bms_core.tasks.store import finish_run
from bms_core.tasks.worker import TASK_COMPLETED_EVENT, TaskWorker

pytestmark = pytest.mark.kiwi_id(2371)

NOW = datetime(2026, 11, 1, 3, 30, 0)
"""固定时钟（naive UTC）。"""

CALLS: ConcurrentStableList[str] = ConcurrentStableList()
"""执行体调用记录（用例间按需清空）。"""

FAIL_TIMES = ConcurrentStableList([0])
"""`_flaky_handler` 剩余失败次数。"""


async def _ok_handler(ctx: TaskContext) -> TaskResult:
    """成功执行体。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: 成功结果。
    """
    CALLS.append(f"ok:{ctx.run.code}")
    return TaskResult.success("done", "output-ok")


async def _boom_handler(ctx: TaskContext) -> TaskResult:
    """持续失败的执行体。

    Args:
        ctx: 执行上下文。

    Raises:
        RuntimeError: 固定抛出。
    """
    CALLS.append("boom")
    raise RuntimeError("handler exploded")


async def _flaky_handler(ctx: TaskContext) -> TaskResult:
    """先失败后成功的执行体（按 `FAIL_TIMES` 递减）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: 成功结果。

    Raises:
        RuntimeError: 仍在失败次数内。
    """
    CALLS.append("flaky")
    if FAIL_TIMES[0] > 0:
        FAIL_TIMES[0] -= 1
        raise RuntimeError("transient")
    return TaskResult.success("recovered")


async def _skip_handler(ctx: TaskContext) -> TaskResult:
    """跳过执行体。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: 跳过结果。
    """
    CALLS.append("skip")
    return TaskResult.skipped("占位实现：归口 03_01")


async def _none_handler(ctx: TaskContext) -> Any:
    """返回 None 的执行体（契约违约，验证兜底错误摘要）。

    Args:
        ctx: 执行上下文。

    Returns:
        Any: 恒 None。
    """
    CALLS.append("none")
    return None


async def _db_handler(ctx: TaskContext) -> TaskResult:
    """需要租户库会话的执行体（验证 `ctx.session()` 开合口注入）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: 成功结果。
    """
    async with ctx.session() as session:
        _ = await session.execute(select(SysTask))
    CALLS.append("db")
    return TaskResult.success("db-ok")


async def _slow_handler(ctx: TaskContext) -> TaskResult:
    """慢执行体（供取消 / 回队用例使用）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: 成功结果。
    """
    CALLS.append("slow")
    await asyncio.sleep(10)
    return TaskResult.success("slow")


_HANDLER_PREFIXES: ConcurrentStableList[str] = ConcurrentStableList([__name__])
"""handler 白名单：本测试模块（执行体就定义在这里）。"""


def _reset() -> None:
    """重置执行体调用记录与失败次数。"""
    CALLS.clear()
    FAIL_TIMES.clear()
    FAIL_TIMES.append(0)


async def _add_task(session: AsyncSession, *, code: str = "task_a") -> int:
    """插入任务定义。

    Args:
        session: 会话。
        code: 任务代码。

    Returns:
        int: 任务主键。
    """
    async with session.begin():
        task = SysTask(code=code, name=code, handler="bms_core.tests.tasks.test_task_worker:_ok_handler")
        session.add(task)
        await session.flush()
        return int(task.id)


async def _add_run(session: AsyncSession, task_id: int, *, run_id: str = "run-1") -> int:
    """插入 running 执行记录。

    Args:
        session: 会话。
        task_id: 任务主键。
        run_id: 执行标识。

    Returns:
        int: 记录主键。
    """
    async with session.begin():
        record = SysTaskLog(task_id=task_id, run_id=run_id, status=TASK_RUN_RUNNING, started_at=NOW)
        session.add(record)
        await session.flush()
        return int(record.id)


def _worker(
    registry: EngineRegistry,
    fake_redis: Redis,
    *,
    max_retries: int = 0,
    metrics: Any = None,
    outbox: Any = None,
) -> TaskWorker:
    """构造执行器（固定时钟、即时退避）。

    Args:
        registry: 引擎注册表。
        fake_redis: 假 Redis。
        max_retries: 重试次数。
        metrics: 指标器。
        outbox: 发件箱存储。

    Returns:
        TaskWorker: 执行器。
    """

    async def _no_sleep(_seconds: float) -> None:
        return None

    return TaskWorker(
        settings=TaskSchedulerSettings(max_retries=max_retries, result_max_chars=8),
        registry=registry,
        queue=TaskQueue(client=fake_redis),
        allowed_handler_prefixes=_HANDLER_PREFIXES,
        outbox=outbox,
        session_factory=SessionFactory(),
        metrics=metrics,
        sleep=_no_sleep,
        clock=lambda: NOW,
    )


def _spec(task_id: int, log_id: int, *, handler: str, code: str = "task_a", args: str | None = None) -> TaskRunSpec:
    """构造运行规格。

    Args:
        task_id: 任务主键。
        log_id: 记录主键。
        handler: 执行体路径。
        code: 任务代码。
        args: 参数原文。

    Returns:
        TaskRunSpec: 运行规格。
    """
    return TaskRunSpec(
        db_key="platform", task_id=task_id, log_id=log_id, run_id="run-1", code=code, handler=handler, args_json=args
    )


async def test_execute_success_writes_log_and_event(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """成功：记录收敛为 success（带耗时 / 输出摘要），并发 `sys.task.completed`。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis)
    await worker._execute(_spec(task_id, log_id, handler=f"{__name__}:_ok_handler"))  # pyright: ignore[reportPrivateUsage]
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
        events = (await session.execute(select(SysOutbox))).scalars().all()
    assert record.status == TASK_RUN_SUCCESS
    assert record.finished_at == NOW
    assert record.cost_time is not None
    assert record.result == "output-…"  # 截断到 8 字符（7 + 省略号）
    assert record.error_msg is None
    assert [item.event_type for item in events] == [TASK_COMPLETED_EVENT]
    assert events[0].payload["task_id"] == str(task_id)
    assert events[0].payload["status"] == TASK_RUN_SUCCESS


async def test_execute_retries_then_succeeds(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """异常按配置重试：第二次成功，`retry_count` 如实记录。"""
    _reset()
    FAIL_TIMES[0] = 1
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis, max_retries=2)
    await worker._execute(_spec(task_id, log_id, handler=f"{__name__}:_flaky_handler"))  # pyright: ignore[reportPrivateUsage]
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_SUCCESS
    assert record.retry_count == 1
    assert CALLS.count("flaky") == 2


async def test_execute_exhausts_retries(registry: EngineRegistry, session: AsyncSession, fake_redis: Redis) -> None:
    """重试耗尽：最终 failed，错误摘要保留，`retry_count` 等于配置次数。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis, max_retries=2, metrics=NullMetrics())
    await worker._execute(_spec(task_id, log_id, handler=f"{__name__}:_boom_handler"))  # pyright: ignore[reportPrivateUsage]
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
        events = (await session.execute(select(SysOutbox))).scalars().all()
    assert record.status == TASK_RUN_FAILED
    assert record.retry_count == 2
    assert record.error_msg is not None
    assert "RuntimeError" in record.error_msg
    assert events[0].payload["status"] == TASK_RUN_FAILED
    assert CALLS.count("boom") == 3


async def test_execute_skipped_result(registry: EngineRegistry, session: AsyncSession, fake_redis: Redis) -> None:
    """跳过是一等终态：记录 skipped，事件照发。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    await _worker(registry, fake_redis)._execute(  # pyright: ignore[reportPrivateUsage]
        _spec(task_id, log_id, handler=f"{__name__}:_skip_handler")
    )
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
        events = (await session.execute(select(SysOutbox))).scalars().all()
    assert record.status == TASK_RUN_SKIPPED
    assert events[0].payload["status"] == TASK_RUN_SKIPPED


async def test_execute_rejects_unregistered_handler(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """白名单外 handler：直接 failed（`70003`），不执行、不重试。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    await _worker(registry, fake_redis, max_retries=3)._execute(  # pyright: ignore[reportPrivateUsage]
        _spec(task_id, log_id, handler="os.system:run")
    )
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_FAILED
    assert record.retry_count == 0
    assert record.error_msg is not None
    assert "白名单" in record.error_msg


async def test_execute_rejects_invalid_args(registry: EngineRegistry, session: AsyncSession, fake_redis: Redis) -> None:
    """参数不可解析：直接 failed（`70004`），不进入执行体。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    await _worker(registry, fake_redis)._execute(  # pyright: ignore[reportPrivateUsage]
        _spec(task_id, log_id, handler=f"{__name__}:_ok_handler", args="{bad json")
    )
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_FAILED
    assert CALLS.count("ok:task_a") == 0


async def test_finish_run_skips_record_already_reclaimed(registry: EngineRegistry, session: AsyncSession) -> None:
    """记录已被超时回收时终态更新不生效（不覆盖既有失败原因）。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    async with session.begin():
        assert (
            await finish_run(
                session, log_id=log_id, status=TASK_RUN_SUCCESS, finished_at=NOW, cost_time=1, retry_count=0
            )
            is True
        )
    async with session.begin():
        assert (
            await finish_run(
                session, log_id=log_id, status=TASK_RUN_FAILED, finished_at=NOW, cost_time=1, retry_count=0
            )
            is False
        )


async def test_handle_outcome_discards_dirty_payload(registry: EngineRegistry, fake_redis: Redis) -> None:
    """脏载荷只记日志并丢弃，不打断消费循环。"""
    _reset()
    worker = _worker(registry, fake_redis, metrics=NullMetrics())
    await worker._handle_outcome(None, "bad payload")  # pyright: ignore[reportPrivateUsage]
    assert CALLS.count("ok:task_a") == 0


async def test_run_once_reports_empty_queue(registry: EngineRegistry, fake_redis: Redis) -> None:
    """队列空：`run_once` 返回 False（不误判为处理成功）。"""
    worker = _worker(registry, fake_redis)
    assert await worker.run_once() is False


async def test_run_once_handles_single_message(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """队列有一条：`run_once` 消费并返回 True。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis)
    await TaskQueue(client=fake_redis).push(_spec(task_id, log_id, handler=f"{__name__}:_ok_handler"))
    assert await worker.run_once() is True
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_SUCCESS


async def test_run_forever_consumes_and_stops(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """长驻消费：取到消息后执行；关闭时停止取新消息。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis)
    await TaskQueue(client=fake_redis).push(_spec(task_id, log_id, handler=f"{__name__}:_ok_handler"))
    runner = asyncio.create_task(worker.run_forever())
    await asyncio.sleep(0.2)
    await worker.aclose()
    await asyncio.gather(runner, return_exceptions=True)
    assert worker.stopping is True
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_SUCCESS


async def test_cancel_requeues_unfinished_message(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """执行中被取消：消息放回队列（宁可重复不可丢）。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    queue = TaskQueue(client=fake_redis)
    worker = _worker(registry, fake_redis)
    spec = _spec(task_id, log_id, handler=f"{__name__}:_slow_handler")
    task = asyncio.create_task(worker._execute(spec))  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert await fake_redis.llen(queue.key) == 1


async def test_outbox_failure_leaves_record_running(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """发件箱写入失败：记录停在 running（交给超时回收），不抛错打断消费。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = _worker(registry, fake_redis, outbox=_BrokenOutbox())
    await worker._execute(_spec(task_id, log_id, handler=f"{__name__}:_ok_handler"))  # pyright: ignore[reportPrivateUsage]
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_RUNNING


async def test_requeue_failure_is_logged_only(registry: EngineRegistry, fake_redis: Redis) -> None:
    """回队失败只记日志（记录留待超时回收），不抛错。"""
    _reset()
    worker = _worker(registry, fake_redis)
    broken = _BrokenQueue()
    worker._queue = broken  # pyright: ignore[reportPrivateUsage]
    await worker._requeue(_spec(1, 1, handler=f"{__name__}:_ok_handler"))  # pyright: ignore[reportPrivateUsage]


class _BrokenOutbox(SqlOutboxStore):
    """发件箱写入必失败的替身。"""

    async def enqueue(self, session: Any, event: Any) -> str:
        """写入即失败。

        Args:
            session: 会话（忽略）。
            event: 事件（忽略）。

        Raises:
            RuntimeError: 固定抛出。
        """
        _ = (session, event)
        raise RuntimeError("outbox down")


class _BrokenQueue(TaskQueue):
    """回队必失败的队列替身。"""

    async def push(self, spec: Any) -> None:
        """入队即失败。

        Args:
            spec: 运行规格（忽略）。

        Raises:
            RuntimeError: 固定抛出。
        """
        _ = spec
        raise RuntimeError("queue down")


async def test_handler_without_result_falls_back_to_failure(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """执行体返回 None（契约违约）：按失败收敛并写兜底摘要。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    await _worker(registry, fake_redis)._execute(  # pyright: ignore[reportPrivateUsage]
        _spec(task_id, log_id, handler=f"{__name__}:_none_handler")
    )
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_FAILED
    assert record.error_msg == "任务执行失败（无错误信息）"


async def test_handler_can_open_tenant_session(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """执行体经 `ctx.session()` 拿到租户库会话（不另起事件循环）。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    await _worker(registry, fake_redis)._execute(  # pyright: ignore[reportPrivateUsage]
        _spec(task_id, log_id, handler=f"{__name__}:_db_handler")
    )
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_SUCCESS
    assert CALLS.count("db") == 1


async def test_handle_outcome_discards_dirty_payload_without_metrics(
    registry: EngineRegistry, fake_redis: Redis
) -> None:
    """未装配指标器时脏消息也只记日志（不因缺指标器报错）。"""
    worker = _worker(registry, fake_redis)
    await worker._handle_outcome(None, None)  # pyright: ignore[reportPrivateUsage]


async def test_aclose_without_run_is_safe(registry: EngineRegistry, fake_redis: Redis) -> None:
    """未启动消费即关闭：空协程清单直接返回（可重复调用）。"""
    worker = _worker(registry, fake_redis)
    await worker.aclose()
    assert worker.stopping is True


async def test_consume_loop_exits_after_timeout_when_stopping(registry: EngineRegistry, fake_redis: Redis) -> None:
    """消费协程：空队列超时后继续等待，置停止标志即退出循环。"""
    worker = _worker(registry, fake_redis)
    loop = asyncio.create_task(worker._consume_loop())  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(1.2)
    await worker.aclose()
    await asyncio.gather(loop, return_exceptions=True)
    assert loop.cancelled() is True or loop.done() is True


async def test_worker_uses_real_clock_by_default(
    registry: EngineRegistry, session: AsyncSession, fake_redis: Redis
) -> None:
    """未注入时钟时取当前 UTC（naive）：终态仍能落库。"""
    _reset()
    task_id = await _add_task(session)
    log_id = await _add_run(session, task_id)
    worker = TaskWorker(
        settings=TaskSchedulerSettings(max_retries=0),
        registry=registry,
        queue=TaskQueue(client=fake_redis),
        allowed_handler_prefixes=_HANDLER_PREFIXES,
        session_factory=SessionFactory(),
    )
    await worker._execute(_spec(task_id, log_id, handler=f"{__name__}:_ok_handler"))  # pyright: ignore[reportPrivateUsage]
    async with session.begin():
        record = (await session.execute(select(SysTaskLog).where(SysTaskLog.id == log_id))).scalar_one()
    assert record.status == TASK_RUN_SUCCESS
