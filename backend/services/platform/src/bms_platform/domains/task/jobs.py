"""平台内建作业：定时任务执行（`sys.task.run`，`BaseJobHandler` 具体实现样例）。

- 任务定义 / 执行记录仍归 `sys_task` / `sys_task_log`；本 handler 只承接「执行」这一段，
  任务历史与任务 API 口径不变；
- 执行体仍受 `[task_scheduler].allowed_handler_prefixes` 白名单约束（作业中心不绕过）；
- 结果映射：`success` → 作业成功；`failed` → 作业失败且**不重试**（任务自身失败，重试只会重复）；
  `skipped` → 作业成功（说明写入任务日志）；执行体抛异常 → 作业可重试，任务日志保持 running
  由下次尝试或租约回收兜底。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.exceptions import TaskArgsInvalidError, TaskHandlerNotRegisteredError
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.events.base import EventEnvelope
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.models.platform.task import (
    TASK_RUN_FAILED,
    TASK_RUN_SKIPPED,
    TASK_RUN_SUCCESS,
)
from bms_core.outbox.store import SqlOutboxStore
from bms_core.tasks.handlers import resolve_handler
from bms_core.tasks.spec import TaskContext, TaskRunSpec, parse_task_args
from bms_core.tasks.store import finish_run

__all__ = ["TASK_COMPLETED_EVENT", "TaskJobHandler"]

_LOGGER = get_logger("bms")

TASK_COMPLETED_EVENT = "sys.task.completed"
"""任务执行完成事件（契约 `deploy/events/contracts.json` v1.0.0）。"""


class TaskJobHandler(BaseJobHandler):
    """执行一条到期的定时任务（`sys.task.run`）。"""

    job_type = "sys.task.run"
    description = "执行一条到期的定时任务（任务定义与执行记录保留在 sys_task / sys_task_log）"

    async def run(self, ctx: JobContext) -> JobResult:
        """解析执行体并执行，结果回写 `sys_task_log`。

        Args:
            ctx: 作业执行上下文（负载含 task_id / log_id / run_id / code / handler / args_json）。

        Returns:
            JobResult: 作业结果。
        """
        payload = ctx.payload
        task_id = int(str(payload.get("task_id") or 0))
        log_id = int(str(payload.get("log_id") or 0))
        run_id = str(payload.get("run_id") or "")
        code = str(payload.get("code") or "")
        handler_path = str(payload.get("handler") or "")
        raw_args = payload.get("args_json")
        args_json = None if raw_args is None else str(raw_args)
        prefixes = get_settings().task_scheduler.allowed_handler_prefixes
        started = time.monotonic()
        try:
            handler = resolve_handler(handler_path, prefixes)
            args = parse_task_args(args_json)
        except (TaskHandlerNotRegisteredError, TaskArgsInvalidError) as exc:
            await self._finish(
                ctx,
                log_id=log_id,
                status=TASK_RUN_FAILED,
                cost_time=_elapsed_ms(started),
                error_text=str(exc),
            )
            return JobResult.failed(str(exc), retryable=False)
        spec = TaskRunSpec(
            db_key=ctx.db_key,
            task_id=task_id,
            log_id=log_id,
            run_id=run_id,
            code=code,
            handler=handler_path,
            args_json=args_json,
            tenant_id=_optional_int(payload.get("tenant_id")),
        )
        task_ctx = TaskContext(run=spec, args=args, open_session=ctx.session)
        try:
            result = await handler(task_ctx)
        except Exception as exc:  # 系统异常：作业可重试，任务日志留待下次尝试 / 超时回收
            _LOGGER.error("定时任务执行异常", task_id=task_id, log_id=log_id, error=str(exc))
            return JobResult.failed(f"{type(exc).__name__}: {exc}", retryable=True)
        await self._finish(
            ctx,
            log_id=log_id,
            status=result.status,
            cost_time=_elapsed_ms(started),
            result_text=result.output,
            error_text=result.message if result.status == TASK_RUN_FAILED else None,
        )
        if result.status == TASK_RUN_SUCCESS:
            return JobResult.success(
                ConcurrentStableDict({"task_id": str(task_id), "log_id": str(log_id)}), message=result.message
            )
        if result.status == TASK_RUN_SKIPPED:
            return JobResult.success(
                ConcurrentStableDict({"task_id": str(task_id), "log_id": str(log_id), "skipped": True}),
                message=result.message,
            )
        return JobResult.failed(result.message or "任务执行失败", retryable=False)

    async def _finish(
        self,
        ctx: JobContext,
        *,
        log_id: int,
        status: str,
        cost_time: int,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> None:
        """回写任务执行记录并写 `sys.task.completed` 事件（同一事务）。

        Args:
            ctx: 执行上下文。
            log_id: 执行记录主键。
            status: 任务终态。
            cost_time: 耗时（毫秒）。
            result_text: 成功输出摘要。
            error_text: 错误摘要。
        """
        async with ctx.session() as session:
            if session.in_transaction():
                await self._write_finish(
                    session,
                    ctx,
                    log_id=log_id,
                    status=status,
                    cost_time=cost_time,
                    result_text=result_text,
                    error_text=error_text,
                )
            else:
                async with session.begin():
                    await self._write_finish(
                        session,
                        ctx,
                        log_id=log_id,
                        status=status,
                        cost_time=cost_time,
                        result_text=result_text,
                        error_text=error_text,
                    )

    async def _write_finish(
        self,
        session: DbSession,
        ctx: JobContext,
        *,
        log_id: int,
        status: str,
        cost_time: int,
        result_text: str | None,
        error_text: str | None,
    ) -> None:
        """在同一会话内回写任务日志并写完成事件。

        Args:
            session: 会话。
            ctx: 执行上下文。
            log_id: 执行记录主键。
            status: 任务终态。
            cost_time: 耗时（毫秒）。
            result_text: 成功输出摘要。
            error_text: 错误摘要。
        """
        await finish_run(
            session,
            log_id=log_id,
            status=status,
            finished_at=_utc_now(),
            cost_time=cost_time,
            retry_count=max(0, ctx.attempt - 1),
            result_text=result_text,
            error_text=error_text,
        )
        envelope = EventEnvelope(
            event_type=TASK_COMPLETED_EVENT,
            payload=ConcurrentStableDict({"task_id": str(ctx.payload.get("task_id") or ""), "status": status}),
            aggregate_key=f"task:{ctx.payload.get('task_id')}",
        )
        await SqlOutboxStore().enqueue(session, envelope)


def _optional_int(value: object) -> int | None:
    """把负载里的租户主键转为 int（None / 空串为空）。

    Args:
        value: 负载值。

    Returns:
        int | None: 租户主键。
    """
    if value is None or value == "":
        return None
    return int(str(value))


def _elapsed_ms(started: float) -> int:
    """计算耗时（毫秒）。

    Args:
        started: `time.monotonic()` 起点。

    Returns:
        int: 毫秒。
    """
    return int((time.monotonic() - started) * 1000)


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)
