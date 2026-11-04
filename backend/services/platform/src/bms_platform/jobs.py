"""平台服务作业 worker 入口：`python -m bms_platform.jobs`。

- 声明本服务 handler（当前 `sys.task.run`）与类型参数；
- 扫描平台链 + 平台租户链，抢占并执行本服务声明的作业；
- `--once` 只跑一轮（诊断 / 冒烟）；长驻由容器命令承载。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.jobs.base import BaseJobHandler
from bms_core.jobs.keys import JobDbKeys
from bms_core.jobs.limits import JobLimits
from bms_core.jobs.registry import JobHandlerRegistry
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.signal import JobChangeSignal
from bms_core.jobs.spec import JobTypeSpec
from bms_core.jobs.worker import JobWorker
from bms_core.workerid.lease import worker_id_lease_sync
from bms_platform.domains.import_export.export_jobs import ExportCleanupJob, ExportExecuteJob
from bms_platform.domains.import_export.jobs import ImportExecuteJob
from bms_platform.domains.task.jobs import TaskJobHandler

__all__ = ["build_runner", "build_worker", "job_handlers", "job_specs", "main"]

SERVICE_KEY = "platform"
"""本服务标识。"""


def job_handlers() -> ConcurrentStableDict[str, BaseJobHandler]:
    """本服务作业处理器（代码侧唯一登记点）。

    Returns:
        ConcurrentStableDict[str, BaseJobHandler]: 作业类型 → 处理器。
    """
    return ConcurrentStableDict(
        {
            TaskJobHandler.job_type: TaskJobHandler(),
            ImportExecuteJob.job_type: ImportExecuteJob(),
            ExportExecuteJob.job_type: ExportExecuteJob(),
            ExportCleanupJob.job_type: ExportCleanupJob(),
        }
    )


def job_specs() -> ConcurrentStableDict[str, JobTypeSpec]:
    """本服务作业类型声明（与 `deploy/registry/platform.toml` 的 `[[jobs]]` 一致）。

    Returns:
        ConcurrentStableDict[str, JobTypeSpec]: 作业类型 → 声明。
    """
    return ConcurrentStableDict(
        {
            "sys.task.run": JobTypeSpec(
                job_type="sys.task.run",
                service_key=SERVICE_KEY,
                domain_key="task",
                handler="bms_platform.domains.task.jobs:TaskJobHandler",
                description="执行一条到期的定时任务（任务定义与执行记录保留在 sys_task / sys_task_log）",
                timeout_seconds=1800,
                max_attempts=3,
                backoff_seconds=30,
                concurrency=4,
            ),
            "platform.import.execute": JobTypeSpec(
                job_type="platform.import.execute",
                service_key=SERVICE_KEY,
                domain_key="import_export",
                handler="bms_platform.domains.import_export.jobs:ImportExecuteJob",
                description="执行 Excel 批量导入（全量原子；错误明细写 sys_job_error）",
                timeout_seconds=1800,
                max_attempts=1,
                backoff_seconds=0,
                concurrency=1,
            ),
            "platform.export.execute": JobTypeSpec(
                job_type="platform.export.execute",
                service_key=SERVICE_KEY,
                domain_key="import_export",
                handler="bms_platform.domains.import_export.export_jobs:ExportExecuteJob",
                description="执行列表导出（Excel / 列表 PDF），产物落对象存储并记入作业结果",
                timeout_seconds=1800,
                max_attempts=1,
                backoff_seconds=0,
                concurrency=2,
            ),
            "platform.export.cleanup": JobTypeSpec(
                job_type="platform.export.cleanup",
                service_key=SERVICE_KEY,
                domain_key="import_export",
                handler="bms_platform.domains.import_export.export_jobs:ExportCleanupJob",
                description="清理过期导出产物（按 export.artifact_ttl 与作业结果里的对象 key）",
                timeout_seconds=1800,
                max_attempts=3,
                backoff_seconds=30,
                concurrency=1,
            ),
        }
    )


def _registry() -> JobHandlerRegistry:
    """构造并装载本服务 handler 注册表。

    Returns:
        JobHandlerRegistry: 注册表。
    """
    registry = JobHandlerRegistry()
    registry.load(job_handlers())
    return registry


def build_runner() -> JobRunner:
    """构造平台作业提交器（进程内提交 / 同步内联）。

    Returns:
        JobRunner: 作业提交器。
    """
    return JobRunner(
        registry=_registry(),
        specs=dict(job_specs()),
        limits=JobLimits(get_settings().jobs),
    )


def build_worker(settings: Settings | None = None) -> tuple[JobWorker, EngineRegistry]:
    """构造平台作业消费者与引擎注册表（调用方负责释放）。

    Args:
        settings: 应用配置；None 取全局单例。

    Returns:
        tuple[JobWorker, EngineRegistry]: worker 与引擎注册表。
    """
    resolved = settings if settings is not None else get_settings()
    factory = EngineFactory(resolved)
    engine_registry = EngineRegistry(factory)
    # 租户注册库 `platform_tenant` 归 tenant 单元：枚举租户需**只读跨读**，
    # 故单独给一个只解析地址的工厂；作业执行仍走严格归属的 engine_registry。
    registry_factory = EngineFactory(resolved, allow_cross_service=True)
    worker = JobWorker(
        service_key=SERVICE_KEY,
        registry=_registry(),
        specs=dict(job_specs()),
        limits=JobLimits(resolved.jobs),
        engine_registry=engine_registry,
        db_keys=JobDbKeys(
            registry_factory=registry_factory,
            service_key=SERVICE_KEY,
            ttl_seconds=resolved.jobs.tenant_cache_ttl_seconds,
        ),
        session_factory=SessionFactory(),
        signal=JobChangeSignal(channel=resolved.jobs.change_channel),
        worker_id=resolved.jobs.worker_id or None,
    )
    return worker, engine_registry


async def _run(args: argparse.Namespace) -> int:
    """运行 worker（单轮或长驻）。

    Args:
        args: 命令行参数。

    Returns:
        int: 退出码。
    """
    worker, engine_registry = build_worker()
    try:
        if args.once:
            report = await worker.run_once()
            print(f"单轮抢占 {report.claimed} 条 / 执行 {report.executed} 条 / 回收 {report.requeued} 条")
            return 0
        print(f"作业 worker 启动：{worker.worker_id}")
        await worker.run_forever()
    except KeyboardInterrupt:
        print("作业 worker 收到中断，已退出")
    finally:
        await worker.aclose()
        await engine_registry.aclose()
    return 0


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码。
    """
    parser = argparse.ArgumentParser(prog="bms_platform.jobs", description="平台服务作业 worker")
    parser.add_argument("--once", action="store_true", help="只跑一轮即退出（诊断 / 冒烟）")
    args = parser.parse_args(None if argv is None else list(argv))
    # WorkerId 租约（03_06）：作业 worker 同样会写库生成雪花 ID，入口取号、退出释放
    with contextlib.suppress(KeyboardInterrupt), worker_id_lease_sync():
        return asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
