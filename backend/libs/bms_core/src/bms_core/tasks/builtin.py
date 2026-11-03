"""内置任务：清单登记 + 执行体（已落地的做真实动作，未落地的仍是占位）。

六条内置任务在 `sys_task` 里有定义（种子入库）、有 cron、有执行记录：

- **孤儿分片清理**（03_01 已落地）：执行体为**触发型**——经服务间调用驱动 file 服务的内部清理端点
  （扫描 / 清理 / 置 `orphan` 全在 file 域，基座不跨库写文件表），返回执行摘要；
- **导出产物清理** / **打印产物清理**（04_03 落地）：同为触发型，分别向 platform / report 服务提交
  `platform.export.cleanup` 与 `print.artifact.cleanup` 作业；两者业务目的同族但数据零耦合
  （不同服务、不同 key 空间、不同保留期参数），故拆为两条独立任务，各自 cron 与任务日志；
- 其余三条仍是占位实现：返回 `skipped` 并在 `message` 里写明归口任务号。理由见详细设计 §4.6：

- 「只登记不执行」会让 handler 白名单直接拒掉、触发即失败，`sys_task_log` 只剩失败记录，
  「还没做」与「做坏了」不可区分；
- 「先把它做出来」要预先猜未定稿的保留期 / 上传中记录口径，后续必然返工。

归口：审计日志归档 → 06_01 / 06_02 / 14；分片表预创建 → 13；软删除残留清理 → 13 回收站 / 14 归档。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.roots import BaseValueObject
from bms_core.jobs.client import JobInternalClient, build_service_client
from bms_core.tasks.spec import TaskContext, TaskResult

__all__ = [
    "BUILTIN_TASK_SPECS",
    "BuiltinTaskSpec",
    "builtin_spec_of",
    "run_archive_audit_logs",
    "run_cleanup_export_artifacts",
    "run_cleanup_orphan_parts",
    "run_cleanup_print_artifacts",
    "run_precreate_shard_tables",
    "run_purge_soft_deleted",
]

_HANDLER_MODULE = "bms_core.tasks.builtin"
"""内置执行体所在模块（handler 白名单前缀的唯一来源）。"""

FILE_SERVICE_KEY = "file"
"""文件服务标识（孤儿回收作业的提供方）。"""

PLATFORM_SERVICE_KEY = "platform"
"""平台服务标识（导出产物清理作业的提供方）。"""

REPORT_SERVICE_KEY = "report"
"""报表打印服务标识（打印产物清理作业的提供方）。"""


@dataclass(frozen=True)
class BuiltinTaskSpec(BaseValueObject):
    """内置任务定义（种子入库依据）。"""

    code: str
    """任务代码（`sys_task.code`，同时是 handler 注册键）。"""

    name: str
    """任务名（`sys_task.name`，运营可见）。"""

    cron: str
    """默认调度表达式（5 段 UTC）。"""

    handler: str
    """执行体点分路径（`module:attr`）。"""

    owner: str
    """真实逻辑的归口任务（占位期写入执行记录，防遗漏）。"""

    summary: str
    """职责一句话（进 `sys_task.remark`）。"""


BUILTIN_TASK_SPECS: ConcurrentStableList[BuiltinTaskSpec] = ConcurrentStableList(
    (
        BuiltinTaskSpec(
            code="cleanup_orphan_parts",
            name="孤儿分片清理",
            cron="0 3 * * *",
            handler=f"{_HANDLER_MODULE}:run_cleanup_orphan_parts",
            owner="03_01（文件管理，经 file.cleanup_orphans 作业执行）",
            summary="回收上传中断遗留的分片对象与超期上传中记录",
        ),
        BuiltinTaskSpec(
            code="cleanup_export_artifacts",
            name="导出产物清理",
            cron="30 3 * * *",
            handler=f"{_HANDLER_MODULE}:run_cleanup_export_artifacts",
            owner="04_03（经 platform.export.cleanup 作业执行）",
            summary="回收过期导出产物（列表导出 Excel / 列表 PDF）",
        ),
        BuiltinTaskSpec(
            code="cleanup_print_artifacts",
            name="打印产物清理",
            cron="45 3 * * *",
            handler=f"{_HANDLER_MODULE}:run_cleanup_print_artifacts",
            owner="04_03（经 print.artifact.cleanup 作业执行）",
            summary="回收过期单据打印产物（批量打印 PDF）",
        ),
        BuiltinTaskSpec(
            code="archive_audit_logs",
            name="审计日志归档",
            cron="0 4 * * *",
            handler=f"{_HANDLER_MODULE}:run_archive_audit_logs",
            owner="06_01 / 06_02（日志与审计）、14（归档）",
            summary="四类审计日志按归档策略迁移（热表 → 归档库 → 对象存储）",
        ),
        BuiltinTaskSpec(
            code="precreate_shard_tables",
            name="分片表预创建",
            cron="0 5 25 * *",
            handler=f"{_HANDLER_MODULE}:run_precreate_shard_tables",
            owner="13（分片与数据访问）",
            summary="提前创建下月分片表（sys_operation_log_yyyyMM 等）",
        ),
        BuiltinTaskSpec(
            code="purge_soft_deleted",
            name="软删除残留物理清理",
            cron="30 4 * * *",
            handler=f"{_HANDLER_MODULE}:run_purge_soft_deleted",
            owner="13（回收站）、14（归档）",
            summary="过期回收站数据物理清理",
        ),
    )
)
"""内置任务清单（唯一来源：种子入库与 `--list` 均取此）。"""


def builtin_spec_of(code: str) -> BuiltinTaskSpec | None:
    """按任务代码取内置任务定义。

    Args:
        code: 任务代码。

    Returns:
        BuiltinTaskSpec | None: 命中返回定义；非内置任务返回 None。
    """
    for spec in BUILTIN_TASK_SPECS:
        if spec.code == code:
            return spec
    return None


def _skipped(owner: str) -> TaskResult:
    """构造占位跳过结果（统一口径：说明 + 归口）。

    Args:
        owner: 归口任务描述。

    Returns:
        TaskResult: `skipped` 结果。
    """
    return TaskResult.skipped(f"占位实现：真实逻辑归口 {owner}；策略定稿后在此实现")


async def _submit_cleanup(*, service_key: str, job_type: str, label: str, ctx: TaskContext) -> TaskResult:
    """向目标服务提交一条清理作业（三条清理任务共用同一提交口径）。

    Args:
        service_key: 作业提供方服务键。
        job_type: 作业类型（须属于该服务声明）。
        label: 中文文案（用于成功 / 失败消息）。
        ctx: 执行上下文。

    Returns:
        TaskResult: 成功带作业标识；下游不可用为失败（由调度器按策略重试提交）。
    """
    today = datetime.now(UTC).date().isoformat()
    tenant_part = ctx.run.tenant_id if ctx.run.tenant_id is not None else "platform"
    try:
        client = JobInternalClient(build_service_client())
        job_id = await client.submit(
            service_key=service_key,
            job_type=job_type,
            payload=ConcurrentStableDict[str, object](),
            idempotency_key=f"{job_type}:{tenant_part}:{today}",
            tenant_id=ctx.run.tenant_id,
        )
    except ServiceUnavailableError as exc:
        return TaskResult.failed(f"{label}作业提交失败：{exc}")
    return TaskResult.success(f"已提交{label}作业 {job_id}", output=f"job_id={job_id}")


async def run_cleanup_orphan_parts(ctx: TaskContext) -> TaskResult:
    """孤儿分片清理（提交型：向 file 服务提交 `file.cleanup_orphans` 作业）。

    Args:
        ctx: 执行上下文（本执行体只提交作业，扫描 / 清理 / 置 `orphan` 全在 file 域）。

    Returns:
        TaskResult: 成功带作业标识；下游不可用为失败（由调度器按策略重试提交）。
    """
    return await _submit_cleanup(
        service_key=FILE_SERVICE_KEY, job_type="file.cleanup_orphans", label="孤儿回收", ctx=ctx
    )


async def run_cleanup_export_artifacts(ctx: TaskContext) -> TaskResult:
    """导出产物清理（提交型：向 platform 服务提交 `platform.export.cleanup` 作业）。

    Args:
        ctx: 执行上下文（本执行体只提交作业，扫描 / 删对象 / 标记全在 platform 域）。

    Returns:
        TaskResult: 成功带作业标识；下游不可用为失败（由调度器按策略重试提交）。
    """
    return await _submit_cleanup(
        service_key=PLATFORM_SERVICE_KEY, job_type="platform.export.cleanup", label="导出产物清理", ctx=ctx
    )


async def run_cleanup_print_artifacts(ctx: TaskContext) -> TaskResult:
    """打印产物清理（提交型：向 report 服务提交 `print.artifact.cleanup` 作业）。

    Args:
        ctx: 执行上下文（本执行体只提交作业，扫描 / 删对象 / 标记全在 report 域）。

    Returns:
        TaskResult: 成功带作业标识；下游不可用为失败（由调度器按策略重试提交）。
    """
    return await _submit_cleanup(
        service_key=REPORT_SERVICE_KEY, job_type="print.artifact.cleanup", label="打印产物清理", ctx=ctx
    )


async def run_archive_audit_logs(ctx: TaskContext) -> TaskResult:
    """审计日志归档（占位）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: `skipped`（归口 06_01 / 06_02 / 14）。
    """
    _ = ctx
    return _skipped("06_01 / 06_02（日志与审计）、14（归档）")


async def run_precreate_shard_tables(ctx: TaskContext) -> TaskResult:
    """分片表预创建（占位）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: `skipped`（归口 13）。
    """
    _ = ctx
    return _skipped("13（分片与数据访问）")


async def run_purge_soft_deleted(ctx: TaskContext) -> TaskResult:
    """软删除残留物理清理（占位）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: `skipped`（归口 13 回收站 / 14 归档）。
    """
    _ = ctx
    return _skipped("13（回收站）、14（归档）")
