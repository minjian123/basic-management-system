"""作业提交与执行：`JobRunner`（提交 / 同步内联 / 取消 / 重试）与 `JobExecutor`（公共执行语义）。

- **提交**：调用方事务内写 `sys_job` 并同事务写 `sys.job.submitted`；幂等键命中直接返回既有作业；
- **同步内联**：`run_inline` 在调用方会话内创建同一记录、置 `running`、执行 handler、收敛终态；
  与异步路径共用同一状态机与终态收敛逻辑（04_01 阈值内导入使用）；
- **执行**：`JobExecutor` 负责上下文装配、进度节流、心跳续租、超时与终态；worker 与 `run_inline` 共用。
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import uuid4

from bms_core.core.exceptions import JobTypeNotRegisteredError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.jobs import store
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.events import (
    completed_envelope,
    enqueue_job_event,
    progress_envelope,
    submitted_envelope,
)
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.spec import JobSnapshot, JobSubmission, JobTypeSpec, dump_payload, now_utc, truncate_text
from bms_core.jobs.store import snapshot_of
from bms_core.models.job import (
    JOB_STATUS_CANCELED,
    JOB_STATUS_DEAD,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    JOB_TERMINAL_STATUSES,
    SysJob,
)
from bms_core.outbox.base import BaseOutboxStore

__all__ = ["JobExecutor", "JobRunner"]

_LOGGER = get_logger("bms")

SessionProvider = Callable[[], AbstractAsyncContextManager[DbSession]]
"""事务内会话提供者（打开时已在事务中；提交 / 回滚由提供者负责）。"""


class JobExecutor(BaseFrameworkObject):
    """公共执行语义：上下文 / 进度 / 心跳 / 超时 / 终态收敛。"""

    def __init__(
        self,
        *,
        limits: JobLimits,
        session_provider: SessionProvider,
        worker_id: str,
        outbox: BaseOutboxStore | None = None,
        heartbeat_enabled: bool = True,
        clock: Callable[[], Any] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """初始化。

        Args:
            limits: 作业生效参数。
            session_provider: 事务内会话提供者（每次调用打开一个短事务）。
            worker_id: 执行者实例标识（心跳与租约持有者）。
            outbox: 发件箱存储（缺省 SQL 实现）。
            heartbeat_enabled: 是否启用心跳续租（同步内联与调用方共事务时关闭）。
            clock: 时钟（测试注入）。
            sleep: 睡眠（测试注入；心跳循环用）。
        """
        self._limits = limits
        self._session_provider = session_provider
        self._worker_id = worker_id
        self._outbox = outbox
        self._heartbeat_enabled = heartbeat_enabled
        self._clock = clock if clock is not None else now_utc
        self._sleep = sleep if sleep is not None else asyncio.sleep
        self._last_progress_at: float | None = None

    async def execute(
        self,
        handler: BaseJobHandler,
        snapshot: JobSnapshot,
        *,
        timeout_seconds: int,
        backoff_seconds: int,
    ) -> JobResult:
        """执行作业并收敛终态。

        Args:
            handler: 作业处理器。
            snapshot: 作业快照（含 db_key / 租约持有者）。
            timeout_seconds: 单次执行超时（秒；0 表示不限）。
            backoff_seconds: 可重试失败的退避基数。

        Returns:
            JobResult: 执行结果（重试回队时仍返回 `failed`）。
        """
        self._last_progress_at = None
        ctx = self._build_context(snapshot)
        heartbeat_task = (
            asyncio.create_task(self._heartbeat_loop(snapshot, self._heartbeat_enabled))
            if self._heartbeat_enabled
            else None
        )
        try:
            result = await self._invoke(handler, ctx, timeout_seconds)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
        await self._finalize(snapshot, result, backoff_seconds=backoff_seconds)
        return result

    async def _invoke(self, handler: BaseJobHandler, ctx: JobContext, timeout_seconds: int) -> JobResult:
        """调用 handler 并统一异常 / 超时语义。

        Args:
            handler: 作业处理器。
            ctx: 执行上下文。
            timeout_seconds: 超时（秒；0 不限）。

        Returns:
            JobResult: 执行结果。
        """
        try:
            if timeout_seconds > 0:
                result = await asyncio.wait_for(handler.run(ctx), timeout=timeout_seconds)
            else:
                result = await handler.run(ctx)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            return JobResult.failed(f"执行超时（>{timeout_seconds}s）", retryable=True)
        except Exception as exc:  # 系统异常默认可重试
            return JobResult.failed(f"{type(exc).__name__}: {exc}", retryable=True)
        if result.status not in (JOB_STATUS_SUCCEEDED, JOB_STATUS_FAILED, JOB_STATUS_CANCELED):
            return JobResult.failed(f"handler 返回非法状态：{result.status}", retryable=False)
        return result

    def _build_context(self, snapshot: JobSnapshot) -> JobContext:
        """构造执行上下文（注入会话 / 进度 / 取消 / 错误写入）。

        Args:
            snapshot: 作业快照。

        Returns:
            JobContext: 执行上下文。
        """

        @asynccontextmanager
        async def _open() -> AsyncGenerator[DbSession]:
            async with self._session_provider() as session:
                yield session

        async def _report(done: int, total: int | None) -> None:
            await self._report_progress(snapshot, done, total)

        async def _cancelled() -> bool:
            async with self._session_provider() as session:
                record = await store.get_job(session, snapshot.id)
                return bool(record is not None and record.cancel_requested)

        async def _write_error(
            message: str, *, row_no: int | None = None, column_key: str | None = None, item_ref: str | None = None
        ) -> None:
            async with self._session_provider() as session:
                await store.add_job_error(
                    session,
                    job_id=snapshot.id,
                    message=message,
                    row_no=row_no,
                    column_key=column_key,
                    item_ref=item_ref,
                )

        return JobContext(
            job_id=snapshot.id,
            job_type=snapshot.job_type,
            service_key=snapshot.service_key,
            db_key=snapshot.db_key,
            payload=snapshot.payload,
            tenant_id=snapshot.tenant_id,
            attempt=max(1, snapshot.attempts),
            max_attempts=snapshot.max_attempts,
            open_session=_open,
            progress_reporter=_report,
            cancel_checker=_cancelled,
            error_writer=_write_error,
        )

    async def _report_progress(self, snapshot: JobSnapshot, done: int, total: int | None) -> None:
        """节流更新进度并发 `sys.job.progress` 事件。

        Args:
            snapshot: 作业快照。
            done: 已完成量。
            total: 总量。
        """
        now = self._clock()
        interval = self._limits.progress_interval_seconds
        is_final = total is not None and done >= total
        monotonic = asyncio.get_running_loop().time()
        if (
            interval > 0
            and not is_final
            and self._last_progress_at is not None
            and monotonic - self._last_progress_at < interval
        ):
            return
        self._last_progress_at = monotonic
        try:
            async with self._session_provider() as session:
                if not await store.update_progress(session, job_id=snapshot.id, done=done, total=total, now=now):
                    return
                await enqueue_job_event(
                    session,
                    progress_envelope(
                        job_id=snapshot.id,
                        job_type=snapshot.job_type,
                        service_key=snapshot.service_key,
                        done=done,
                        total=total,
                    ),
                    outbox=self._outbox,
                )
        except Exception as exc:  # 进度失败不反噬执行，下次心跳 / 进度重试
            _LOGGER.warning("作业进度更新失败（不影响执行）", job_id=snapshot.id, error=str(exc))

    async def _heartbeat_loop(self, snapshot: JobSnapshot, enabled: bool) -> None:
        """执行期间周期续租（失败只告警，租约到期由其他 worker 回收）。

        Args:
            snapshot: 作业快照。
            enabled: 是否启用。
        """
        if not enabled:
            return
        try:
            while True:
                await self._sleep(self._limits.heartbeat_interval_seconds)
                now = self._clock()
                async with self._session_provider() as session:
                    alive = await store.heartbeat(
                        session,
                        job_id=snapshot.id,
                        worker_id=self._worker_id,
                        lease_until=now + timedelta(seconds=self._limits.lease_seconds),
                        now=now,
                    )
                if not alive:
                    _LOGGER.warning("作业心跳失败（租约已失效，等待回收）", job_id=snapshot.id)
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 心跳故障不打断执行
            _LOGGER.warning("作业心跳异常（租约到期后由其他 worker 回收）", job_id=snapshot.id, error=str(exc))

    async def _finalize(self, snapshot: JobSnapshot, result: JobResult, *, backoff_seconds: int) -> None:
        """按结果收敛终态（成功 / 失败 / 取消 / 死信 / 重试回队）并写事件。

        Args:
            snapshot: 作业快照。
            result: 执行结果。
            backoff_seconds: 可重试失败的退避基数。
        """
        now = self._clock()
        if result.status == JOB_STATUS_CANCELED:
            await self._finish(snapshot, JOB_STATUS_CANCELED, now, error_text=result.message or None)
            return
        if result.status == JOB_STATUS_SUCCEEDED:
            result_text = truncate_text(
                dump_payload(result.output) if result.output is not None else None, self._limits.result_max_chars
            )
            await self._finish(snapshot, JOB_STATUS_SUCCEEDED, now, result_text=result_text)
            return
        error_text = truncate_text(result.message or "执行失败", self._limits.error_max_chars)
        if not result.retryable:
            await self._finish(snapshot, JOB_STATUS_FAILED, now, error_text=error_text)
            return
        if snapshot.attempts >= snapshot.max_attempts:
            await self._finish(snapshot, JOB_STATUS_DEAD, now, error_text=error_text)
            return
        delay = min(
            backoff_seconds * (2 ** max(0, snapshot.attempts - 1)),
            self._limits.backoff_max_seconds,
        )
        async with self._session_provider() as session:
            await store.requeue_job(
                session,
                job_id=snapshot.id,
                next_run_at=now + timedelta(seconds=delay),
                error_text=error_text,
                now=now,
            )

    async def _finish(
        self,
        snapshot: JobSnapshot,
        status: str,
        now: Any,
        *,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> None:
        """写终态并同事务写 `sys.job.completed`。

        Args:
            snapshot: 作业快照。
            status: 终态。
            now: 当前时刻。
            result_text: 结果 JSON。
            error_text: 错误摘要。
        """
        async with self._session_provider() as session:
            updated = await store.finish_job(
                session,
                job_id=snapshot.id,
                status=status,
                finished_at=now,
                result_text=result_text,
                error_text=error_text,
            )
            if not updated:
                return
            await enqueue_job_event(
                session,
                completed_envelope(
                    job_id=snapshot.id,
                    job_type=snapshot.job_type,
                    service_key=snapshot.service_key,
                    status=status,
                    attempts=snapshot.attempts,
                    error=error_text,
                ),
                outbox=self._outbox,
            )


class JobRunner(BaseFrameworkObject):
    """作业提交与同步内联（进程内入口；跨服务提交走 `JobInternalClient`）。"""

    def __init__(
        self,
        *,
        registry: JobHandlerRegistry,
        specs: Mapping[str, JobTypeSpec],
        limits: JobLimits,
        outbox: BaseOutboxStore | None = None,
        clock: Callable[[], Any] | None = None,
    ) -> None:
        """初始化。

        Args:
            registry: 本服务 handler 注册表。
            specs: 本服务作业类型声明（`job_type → JobTypeSpec`）。
            limits: 作业生效参数。
            outbox: 发件箱存储。
            clock: 时钟（测试注入）。
        """
        self._registry = registry
        self._specs = dict(specs)
        self._limits = limits
        self._outbox = outbox
        self._clock = clock if clock is not None else now_utc

    def spec_of(self, job_type: str) -> JobTypeSpec:
        """取作业类型声明。

        Args:
            job_type: 作业类型。

        Returns:
            JobTypeSpec: 类型声明。

        Raises:
            JobTypeNotRegisteredError: 本服务未声明该类型（`71002`）。
        """
        spec = self._specs.get(job_type)
        if spec is None:
            raise JobTypeNotRegisteredError(f"作业类型未在本服务声明：{job_type}")
        return spec

    async def submit(
        self,
        session: DbSession,
        submission: JobSubmission,
        *,
        tenant_id: int | None = None,
    ) -> SysJob:
        """提交作业（同事务写记录与 `sys.job.submitted` 事件）。

        Args:
            session: 作业所在库会话（调用方事务）。
            submission: 提交规格。
            tenant_id: 租户主键（平台链为 None）。

        Returns:
            SysJob: 作业记录（幂等命中返回既有记录）。

        Raises:
            JobTypeNotRegisteredError: 未声明（`71002`）。
            JobHandlerNotRegisteredError: 代码侧 handler 缺失（`71006`）。
        """
        spec = self.spec_of(submission.job_type)
        max_attempts = submission.max_attempts or spec.max_attempts
        record, created = await store.submit_job(
            session,
            submission=submission,
            service_key=spec.service_key,
            domain_key=spec.domain_key,
            max_attempts=max_attempts,
            tenant_id=tenant_id,
            now=self._clock(),
        )
        if created:
            await enqueue_job_event(
                session,
                submitted_envelope(
                    job_id=int(record.id),
                    job_type=record.job_type,
                    service_key=record.service_key,
                    status=record.status,
                ),
                outbox=self._outbox,
            )
        return record

    async def cancel(self, session: DbSession, job_id: int, *, reason: str | None = None) -> str:
        """请求取消。

        Args:
            session: 作业所在库会话。
            job_id: 作业主键。
            reason: 取消原因。

        Returns:
            str: `canceled` / `requested` / `terminal` / `missing`。
        """
        return await store.request_cancel(session, job_id=job_id, now=self._clock(), reason=reason)

    async def retry(self, session: DbSession, job_id: int) -> str:
        """人工重试（仅 dead / failed）。

        Args:
            session: 作业所在库会话。
            job_id: 作业主键。

        Returns:
            str: `retried` / `terminal` / `missing`。
        """
        return (await store.retry_job(session, job_id=job_id, now=self._clock())).status

    async def run_inline(
        self,
        session: DbSession,
        submission: JobSubmission,
        *,
        db_key: str,
        tenant_id: int | None = None,
    ) -> tuple[SysJob, JobResult]:
        """同步内联执行（与异步共用同一记录与状态机）。

        调用方持有事务：作业记录、进度与终态都写在同一会话内，由调用方提交 / 回滚；
        handler 经 `ctx.session()` 拿到同一会话（业务数据与作业记录原子）。

        Args:
            session: 作业所在库会话（调用方事务）。
            submission: 提交规格。
            db_key: 作业所在库键。
            tenant_id: 租户主键。

        Returns:
            tuple[SysJob, JobResult]: （作业记录, 执行结果）。
        """
        record = await self.submit(session, submission, tenant_id=tenant_id)
        if record.status in JOB_TERMINAL_STATUSES or record.status == JOB_STATUS_RUNNING:
            return record, JobResult.success(message=f"幂等命中既有作业（{record.status}）")
        if record.status != JOB_STATUS_QUEUED:
            return record, JobResult.failed(f"作业状态不可执行：{record.status}", retryable=False)
        spec = self.spec_of(record.job_type)
        handler = self._registry.get(record.job_type)
        worker_id = f"inline-{os.getpid()}-{uuid4().hex[:8]}"
        now = self._clock()
        claimed = await store.claim_job(
            session,
            job_id=int(record.id),
            worker_id=worker_id,
            lease_until=now + timedelta(seconds=self._limits.lease_seconds),
            now=now,
        )
        if not claimed:
            return record, JobResult.failed("作业已被其他执行者抢占", retryable=True)
        await session.refresh(record)
        snapshot = snapshot_of(record)
        snapshot = _with_runtime(snapshot, db_key=db_key, lease_owner=worker_id)
        executor = JobExecutor(
            limits=self._limits,
            session_provider=_fixed_session(session),
            worker_id=worker_id,
            outbox=self._outbox,
            heartbeat_enabled=False,
            clock=self._clock,
        )
        result = await executor.execute(
            handler, snapshot, timeout_seconds=spec.timeout_seconds, backoff_seconds=spec.backoff_seconds
        )
        await session.refresh(record)
        return record, result


def _with_runtime(snapshot: JobSnapshot, *, db_key: str, lease_owner: str) -> JobSnapshot:
    """补齐快照的运行期字段（库键 / 租约持有者）。

    Args:
        snapshot: 原始快照。
        db_key: 库键。
        lease_owner: 租约持有者。

    Returns:
        JobSnapshot: 补齐后的快照。
    """
    return replace(snapshot, db_key=db_key, lease_owner=lease_owner)


def _fixed_session(session: DbSession) -> SessionProvider:
    """把已打开的会话包装成会话提供者（不 begin / 不 commit）。

    Args:
        session: 调用方会话。

    Returns:
        SessionProvider: 会话提供者。
    """

    @asynccontextmanager
    async def _provider() -> AsyncGenerator[DbSession]:
        yield session

    return _provider
