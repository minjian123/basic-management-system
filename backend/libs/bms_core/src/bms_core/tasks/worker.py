"""任务执行器（worker）：消费队列 → 解析执行体 → 执行（应用内重试）→ 终态落库 + 落事件。

关键口径（《详细设计 · 任务调度》§4.4）：

- **重试在应用内完成**（退避 `backoff × 2^(n-1)`），不把失败消息丢回队列靠 broker 反复重投——
  否则重试次数会被「应用内 N 次 × broker 重投」放大，并阻塞后续消息；
- **只对异常重试**：执行体主动返回 `failed` 视为「确定的失败」，重试也不会变好；
- **终态必发事件**：`success` / `failed` / `skipped` 三态都发 `sys.task.completed`（重试中间态不发），
  与执行记录**同一事务**写入 `sys_outbox`（生产一致性口径不变，由既有投递器转发）；
- **停机先排水**：置停止标志 → 不再 `BRPOP` → 等在途完成 → 未完成消息 `LPUSH` 回队，
  宁可重复不可丢（重复执行有执行记录可查，丢失则无从追溯）。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import TaskSchedulerSettings
from bms_core.core.exceptions import TaskArgsInvalidError, TaskHandlerNotRegisteredError
from bms_core.core.logging import get_logger
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.events.base import EventEnvelope
from bms_core.metrics.base import BaseMetrics
from bms_core.models.platform.task import TASK_RUN_FAILED
from bms_core.outbox.base import BaseOutboxStore
from bms_core.outbox.store import SqlOutboxStore
from bms_core.tasks.handlers import resolve_handler
from bms_core.tasks.queue import TaskQueue
from bms_core.tasks.spec import TaskContext, TaskResult, TaskRunSpec, parse_task_args
from bms_core.tasks.store import finish_run

__all__ = ["TASK_COMPLETED_EVENT", "TaskWorker"]

_LOGGER = get_logger("bms")

TASK_COMPLETED_EVENT = "sys.task.completed"
"""任务执行完成事件（契约 `deploy/events/contracts.json` v1.0.0）。"""


class TaskWorker(BaseAsyncResource):
    """队列消费者（多副本横向扩展；`ops/task_scheduler.py --worker` 承载）。"""

    def __init__(
        self,
        *,
        settings: TaskSchedulerSettings,
        registry: EngineRegistry,
        queue: TaskQueue,
        allowed_handler_prefixes: ConcurrentStableList[str],
        outbox: BaseOutboxStore | None = None,
        session_factory: SessionFactory | None = None,
        metrics: BaseMetrics | None = None,
        sleep: Any = None,
        clock: Any = None,
    ) -> None:
        """初始化。

        Args:
            settings: 调度参数（并发 / 重试 / 截断 / 队列键）。
            registry: 引擎注册表（按载荷里的库键开会话）。
            queue: 待执行队列。
            allowed_handler_prefixes: handler 模块前缀白名单。
            outbox: 发件箱存储（缺省 SQL 实现）。
            session_factory: 会话工厂（测试注入）。
            metrics: 指标记录器（None 表示不记录）。
            sleep: 退避睡眠（测试注入，避免真实等待）。
            clock: 时钟（naive UTC；测试注入固定时刻）。
        """
        self._settings = settings
        self._registry = registry
        self._queue = queue
        self._prefixes = allowed_handler_prefixes
        self._outbox = outbox if outbox is not None else SqlOutboxStore()
        self._session_factory = session_factory
        self._metrics = metrics
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._clock = clock if clock is not None else _utc_now_naive
        self._stopping = asyncio.Event()
        self._workers: ConcurrentStableList[asyncio.Task[None]] = ConcurrentStableList()

    @property
    def stopping(self) -> bool:
        """是否已置停止标志。

        Returns:
            bool: 已停止 True。
        """
        return self._stopping.is_set()

    async def aclose(self) -> None:
        """停止消费：置标志、取消消费协程（在途执行体收到取消后由各自逻辑回队）。"""
        self._stopping.set()
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = ConcurrentStableList()

    async def run_forever(self) -> None:
        """启动 `worker_concurrency` 个消费协程并等待其结束（取消或停止）。"""
        self._stopping.clear()
        self._workers = ConcurrentStableList(
            asyncio.create_task(self._consume_loop()) for _ in range(self._settings.worker_concurrency)
        )
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def run_once(self) -> bool:
        """消费一条即返回（诊断 / 冒烟）。

        Returns:
            bool: 处理了一条 True；队列空 False。
        """
        outcome = await self._queue.pop(timeout=1)
        if outcome.timed_out:
            return False
        await self._handle_outcome(outcome.spec, outcome.error)
        return True

    async def _consume_loop(self) -> None:
        """单消费协程：`BRPOP` → 处理（停止标志置位后不再取新消息）。"""
        while not self._stopping.is_set():
            outcome = await self._queue.pop(timeout=1)
            if outcome.timed_out:
                continue
            await self._handle_outcome(outcome.spec, outcome.error)

    async def _handle_outcome(self, spec: TaskRunSpec | None, error: str | None) -> None:
        """处理一次出队结果（脏消息只记日志，不打断循环）。

        Args:
            spec: 运行规格（脏消息为 None）。
            error: 解析错误（正常为 None）。
        """
        if spec is None:
            if self._metrics is not None:
                await self._metrics.counter("bms_task_run_total", value=1.0, labels={"code": "?", "status": "dirty"})
            _LOGGER.error("任务队列载荷不可解析，已丢弃", error=error or "")
            return
        await self._execute(spec)

    async def _execute(self, spec: TaskRunSpec) -> None:
        """执行一条任务并收敛终态。

        Args:
            spec: 运行规格。
        """
        started = time.monotonic()
        attempt = 0
        result: TaskResult | None = None
        error_text: str | None = None
        try:
            handler = resolve_handler(spec.handler, self._prefixes)
        except TaskHandlerNotRegisteredError as exc:
            error_text = str(exc)
        else:
            result, attempt, error_text = await self._run_with_retry(spec, handler)
        if result is None and error_text is None:
            error_text = "任务执行失败（无错误信息）"
        status = result.status if result is not None else TASK_RUN_FAILED
        cost_time = int((time.monotonic() - started) * 1000)
        await self._finalize(
            spec,
            status=status,
            cost_time=cost_time,
            retry_count=attempt,
            result_text=_truncate(result.output, self._settings.result_max_chars) if result is not None else None,
            error_text=_truncate(error_text, self._settings.error_max_chars),
        )

    async def _run_with_retry(self, spec: TaskRunSpec, handler: Any) -> tuple[TaskResult | None, int, str | None]:
        """执行体调用与退避重试（只对异常重试）。

        Args:
            spec: 运行规格。
            handler: 执行体。

        Returns:
            tuple[TaskResult | None, int, str | None]: （结果, 重试次数, 错误摘要）。
        """
        attempt = 0
        try:
            context = TaskContext(
                run=spec, args=parse_task_args(spec.args_json), open_session=self._opener(spec.db_key)
            )
        except TaskArgsInvalidError as exc:
            return None, attempt, str(exc)
        while True:
            try:
                return await handler(context), attempt, None
            except asyncio.CancelledError:
                await self._requeue(spec)
                raise
            except Exception as exc:  # 执行体异常统一转失败记录（业务码由执行体自行判定）
                if attempt >= self._settings.max_retries:
                    return None, attempt, f"{type(exc).__name__}: {exc}"
                attempt += 1
                if self._metrics is not None:
                    await self._metrics.counter("bms_task_retry_total", value=1.0, labels={"code": spec.code})
                await self._sleep(self._settings.retry_backoff_seconds * (2 ** (attempt - 1)))

    def _opener(self, db_key: str) -> Any:
        """构造租户库会话开合口（执行体经 `ctx.session()` 取会话）。

        Args:
            db_key: 租户库键。

        Returns:
            Any: 无参可调用对象，返回异步上下文管理器。
        """

        def _open() -> Any:
            return session_scope(self._registry, db_key=db_key, factory=self._session_factory)

        return _open

    async def _finalize(
        self,
        spec: TaskRunSpec,
        *,
        status: str,
        cost_time: int,
        retry_count: int,
        result_text: str | None,
        error_text: str | None,
    ) -> None:
        """同事务收敛执行记录并写 `sys.task.completed` 事件。

        Args:
            spec: 运行规格。
            status: 终态。
            cost_time: 耗时（毫秒）。
            retry_count: 重试次数。
            result_text: 成功输出摘要。
            error_text: 错误摘要。
        """
        moment = self._clock()
        envelope = _completed_envelope(spec, status)
        try:
            async with (
                session_scope(self._registry, db_key=spec.db_key, factory=self._session_factory) as session,
                session.begin(),
            ):
                await finish_run(
                    session,
                    log_id=spec.log_id,
                    status=status,
                    finished_at=moment,
                    cost_time=cost_time,
                    retry_count=retry_count,
                    result_text=result_text,
                    error_text=error_text,
                )
                await self._outbox.enqueue(session, envelope)
        except Exception as exc:  # 落库失败不吞：记录并让 running 记录留给超时回收
            _LOGGER.error("任务终态落库失败（记录留待超时回收）", task_id=spec.task_id, error=str(exc))
            return
        if self._metrics is not None:
            await self._metrics.counter("bms_task_run_total", value=1.0, labels={"code": spec.code, "status": status})

    async def _requeue(self, spec: TaskRunSpec) -> None:
        """取消时把未完成消息放回队列（宁可重复不可丢）。

        Args:
            spec: 运行规格。
        """
        try:
            await self._queue.push(spec)
        except Exception as exc:  # 回队失败只能依赖超时回收，记 error 便于对账
            _LOGGER.error("任务回队失败（记录留待超时回收）", task_id=spec.task_id, error=str(exc))


def _completed_envelope(spec: TaskRunSpec, status: str) -> EventEnvelope:
    """构造 `sys.task.completed` 事件信封。

    Args:
        spec: 运行规格。
        status: 终态。

    Returns:
        EventEnvelope: 事件信封。
    """
    return EventEnvelope(
        event_type=TASK_COMPLETED_EVENT,
        payload=ConcurrentStableDict({"task_id": str(spec.task_id), "status": status}),
        aggregate_key=f"task:{spec.task_id}",
    )


def _truncate(text: str | None, limit: int) -> str | None:
    """按上限截断文本。

    Args:
        text: 文本。
        limit: 上限字符数。

    Returns:
        str | None: 截断结果；入参为 None 返回 None。
    """
    if text is None:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _utc_now_naive() -> datetime:
    """当前 UTC 时间（naive，与表列同形）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)
