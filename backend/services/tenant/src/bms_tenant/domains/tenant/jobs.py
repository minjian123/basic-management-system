"""租户服务作业处理器（任务 `04_03-02`）：到期扫描 + 单租户清理。

两段分开的理由：扫描只「查到期 → 逐租户提交作业」，删库在独立作业里做——单租户失败互不影响，
重试粒度是「一个租户」而不是「一整轮扫描」。

- `tenant.purge.scan`：回填保留期 + 取到期租户 + 逐租户提交 `tenant.purge`（`idempotency_key` 带
  `租户主键 + 版本 + 日期`：同日不重复提交、次日可再提交，避免死信后永远卡住）；
- `tenant.purge`：注册行不存在 / 已恢复 / 未到期 → `skipped`（幂等、零副作用）；逐库删成功才删注册行
  并落 `tenant.purged`；有失败则不删注册行并返回失败（作业框架按策略重试，超限进死信 + 告警）。

作业**落在平台链**（`tenant_id = None`）：`sys_job` 写本服务平台库，不能写进即将被删的租户库——
否则「删完库连带删掉作业记录」，失败重试与留痕同时丢失。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings, get_settings
from bms_core.db.session import DbSession
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission, JobTypeSpec
from bms_core.outbox.store import SqlOutboxStore
from bms_tenant.domains.tenant.services.tenant_purge import (
    DEFAULT_PURGE_BATCH_SIZE,
    PurgeOutcome,
    TenantPurgeService,
)

__all__ = [
    "DOMAIN_KEY",
    "SERVICE_KEY",
    "TENANT_PURGE_JOB_TYPE",
    "TENANT_PURGE_SCAN_JOB_TYPE",
    "TenantPurgeJob",
    "TenantPurgeScanJob",
    "job_handlers",
    "job_specs",
]

SERVICE_KEY = "tenant"
"""本服务标识（作业提供方）。"""

DOMAIN_KEY = "tenant"
"""本业务域（`[[domains]] domain_key = "tenant"`）。"""

TENANT_PURGE_JOB_TYPE = "tenant.purge"
"""单租户清理作业类型。"""

TENANT_PURGE_SCAN_JOB_TYPE = "tenant.purge.scan"
"""到期扫描作业类型（每日一次，由内置任务 `purge_deleted_tenants` 提交）。"""

PurgeServiceFactory = Callable[[DbSession], TenantPurgeService]
"""清理服务工厂（缺省按应用配置装配；测试注入替身以便固定 `now` 与删库执行器）。"""


class TenantPurgeJob(BaseJobHandler):
    """单租户物理清理（逐库删 → 删注册行 → 落 `tenant.purged`）。"""

    job_type = TENANT_PURGE_JOB_TYPE
    description = "清理到期注销租户：逐库删库、删注册行并落 tenant.purged"

    def __init__(
        self,
        *,
        outbox: SqlOutboxStore | None = None,
        settings: Settings | None = None,
        service_factory: PurgeServiceFactory | None = None,
    ) -> None:
        """初始化（能力实现可注入，便于单测与排障）。

        Args:
            outbox: 发件箱（None 用 SQL 实现）。
            settings: 应用配置（None 取全局单例）。
            service_factory: 清理服务工厂（None 按上面的能力装配）。
        """
        self._outbox = outbox
        self._settings = settings
        self._service_factory = service_factory

    def _service(self, session: DbSession) -> TenantPurgeService:
        """按注入优先构造清理服务。

        Args:
            session: 平台库会话。

        Returns:
            TenantPurgeService: 清理服务。
        """
        if self._service_factory is not None:
            return self._service_factory(session)
        settings = self._settings if self._settings is not None else get_settings()
        return TenantPurgeService(
            session=session,
            outbox=self._outbox if self._outbox is not None else SqlOutboxStore(),
            settings=settings,
        )

    async def run(self, ctx: JobContext) -> JobResult:
        """执行单租户清理。

        Args:
            ctx: 作业执行上下文（负载需带 `tenant_id`）。

        Returns:
            JobResult: 已清理 / 跳过为成功；有库删除失败为失败（可重试）。
        """
        raw = ctx.payload.get("tenant_id")
        try:
            tenant_id = int(str(raw))
        except TypeError, ValueError:
            return JobResult.failed("作业负载缺少合法的 tenant_id", retryable=False)
        async with ctx.session() as session:
            outcome = await self._service(session).purge(tenant_id)
        output = _purge_output(tenant_id, outcome)
        if outcome.status == "failed":
            return JobResult.failed(outcome.reason, output=output)
        if outcome.status == "skipped":
            return JobResult.success(output, message=f"租户 {tenant_id} 未清理：{outcome.reason}")
        return JobResult.success(output, message=f"租户 {tenant_id} 已清理（{len(outcome.dropped_services)} 个库）")


class TenantPurgeScanJob(BaseJobHandler):
    """到期扫描（回填保留期 + 逐租户提交清理作业）。"""

    job_type = TENANT_PURGE_SCAN_JOB_TYPE
    description = "扫描到期注销租户：回填保留期并逐租户提交 tenant.purge"

    def __init__(
        self,
        *,
        outbox: SqlOutboxStore | None = None,
        settings: Settings | None = None,
        service_factory: PurgeServiceFactory | None = None,
    ) -> None:
        """初始化（能力实现可注入，便于单测与排障）。

        Args:
            outbox: 发件箱（None 用 SQL 实现）。
            settings: 应用配置（None 取全局单例）。
            service_factory: 清理服务工厂（None 按上面的能力装配）。
        """
        self._outbox = outbox
        self._settings = settings
        self._service_factory = service_factory

    def _service(self, session: DbSession) -> TenantPurgeService:
        """按注入优先构造清理服务。

        Args:
            session: 平台库会话。

        Returns:
            TenantPurgeService: 清理服务。
        """
        if self._service_factory is not None:
            return self._service_factory(session)
        settings = self._settings if self._settings is not None else get_settings()
        return TenantPurgeService(
            session=session,
            outbox=self._outbox if self._outbox is not None else SqlOutboxStore(),
            settings=settings,
        )

    async def run(self, ctx: JobContext) -> JobResult:
        """执行一轮扫描并提交清理作业。

        Args:
            ctx: 作业执行上下文（可选负载 `batch_size`）。

        Returns:
            JobResult: 成功带回填数 / 到期数 / 提交数；提交异常由执行器统一转失败。
        """
        batch_size = _batch_size(ctx.payload)
        async with ctx.session() as session:
            outcome = await self._service(session).scan(batch_size=batch_size)
            runner = _runner()
            today = datetime.now(UTC).date().isoformat()
            submitted = 0
            for target in outcome.targets:
                await runner.submit(
                    session,
                    JobSubmission(
                        job_type=TENANT_PURGE_JOB_TYPE,
                        payload=ConcurrentStableDict(
                            {"tenant_id": str(target.tenant_id), "db_key": target.code, "version": target.version}
                        ),
                        # 同日不重复提交（扫描可能被重跑）；次日可再提交——死信后仍有机会收敛。
                        idempotency_key=f"{TENANT_PURGE_JOB_TYPE}:{target.tenant_id}:{target.version}:{today}",
                    ),
                    tenant_id=None,
                )
                submitted += 1
            await session.commit()
        await ctx.report_progress(submitted, len(outcome.targets))
        return JobResult.success(
            ConcurrentStableDict(
                {"backfilled": outcome.backfilled, "due": len(outcome.targets), "submitted": submitted}
            ),
            message=f"扫描完成：回填 {outcome.backfilled} / 到期 {len(outcome.targets)} / 提交 {submitted}",
        )


def job_handlers() -> ConcurrentStableDict[str, BaseJobHandler]:
    """本服务作业处理器（代码侧唯一登记点）。

    Returns:
        ConcurrentStableDict[str, BaseJobHandler]: 作业类型 → 处理器。
    """
    return ConcurrentStableDict(
        {
            TenantPurgeScanJob.job_type: TenantPurgeScanJob(),
            TenantPurgeJob.job_type: TenantPurgeJob(),
        }
    )


def job_specs() -> ConcurrentStableDict[str, JobTypeSpec]:
    """本服务作业类型声明（须与 `deploy/registry/platform.toml` 的 `[[jobs]]` 一致）。

    Returns:
        ConcurrentStableDict[str, JobTypeSpec]: 作业类型 → 声明。
    """
    return ConcurrentStableDict(
        {
            TENANT_PURGE_SCAN_JOB_TYPE: JobTypeSpec(
                job_type=TENANT_PURGE_SCAN_JOB_TYPE,
                service_key=SERVICE_KEY,
                domain_key=DOMAIN_KEY,
                handler="bms_tenant.domains.tenant.jobs:TenantPurgeScanJob",
                description="扫描到期注销租户：回填保留期并逐租户提交 tenant.purge",
                timeout_seconds=600,
                max_attempts=3,
                backoff_seconds=60,
                concurrency=1,
            ),
            TENANT_PURGE_JOB_TYPE: JobTypeSpec(
                job_type=TENANT_PURGE_JOB_TYPE,
                service_key=SERVICE_KEY,
                domain_key=DOMAIN_KEY,
                handler="bms_tenant.domains.tenant.jobs:TenantPurgeJob",
                description="清理到期注销租户：逐库删库、删注册行并落 tenant.purged",
                timeout_seconds=1800,
                max_attempts=3,
                backoff_seconds=120,
                concurrency=1,
            ),
        }
    )


def _runner() -> JobRunner:
    """构造本服务作业提交器（进程内提交；扫描作业用它逐租户落 `tenant.purge`）。

    Returns:
        JobRunner: 作业提交器。
    """
    registry = JobHandlerRegistry()
    registry.load(job_handlers())
    return JobRunner(
        registry=registry,
        specs=dict(job_specs()),
        limits=JobLimits(get_settings().jobs),
    )


def _batch_size(payload: ConcurrentStableDict[str, object]) -> int:
    """取扫描批大小（负载可覆盖；非法值回落缺省）。

    Args:
        payload: 作业负载。

    Returns:
        int: 批大小（恒 > 0）。
    """
    raw = payload.get("batch_size")
    if raw is None:
        return DEFAULT_PURGE_BATCH_SIZE
    try:
        value = int(str(raw))
    except TypeError, ValueError:
        return DEFAULT_PURGE_BATCH_SIZE
    return value if value > 0 else DEFAULT_PURGE_BATCH_SIZE


def _purge_output(tenant_id: int, outcome: PurgeOutcome) -> ConcurrentStableDict[str, object]:
    """构造作业结果摘要（作业记录即清理留痕之一）。

    Args:
        tenant_id: 租户主键。
        outcome: 清理结果。

    Returns:
        ConcurrentStableDict[str, object]: 结果摘要。
    """
    output: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "tenant_id": str(tenant_id),
            "status": outcome.status,
            "dropped_services": len(outcome.dropped_services),
            "failed_services": len(outcome.failed_services),
        }
    )
    if outcome.db_basis:
        output.set("db_key", outcome.db_basis)
    if outcome.reason:
        output.set("reason", outcome.reason)
    if outcome.failed_services:
        output.set("failed_service_keys", ",".join(outcome.failed_services))
    return output
