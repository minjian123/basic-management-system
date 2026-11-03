"""内置任务：清单登记 + 执行体（已落地的做真实动作，未落地的仍是占位）。

七条内置任务在 `sys_task` 里有定义（种子入库）、有 cron、有执行记录：

- **孤儿分片清理**（03_01 已落地）：执行体为**触发型**——经服务间调用驱动 file 服务的内部清理端点
  （扫描 / 清理 / 置 `orphan` 全在 file 域，基座不跨库写文件表），返回执行摘要；
- **导出产物清理** / **打印产物清理**（04_03 落地）：同为触发型，分别向 platform / report 服务提交
  `platform.export.cleanup` 与 `print.artifact.cleanup` 作业；两者业务目的同族但数据零耦合
  （不同服务、不同 key 空间、不同保留期参数），故拆为两条独立任务，各自 cron 与任务日志；
- **审计链巡检**（06_01 落地）：触发型——向 platform 服务提交校验请求，逐类日志校验当前保留期内分片链。
- 其余两条仍是占位实现：返回 `skipped` 并在 `message` 里写明归口任务号。理由见详细设计 §4.6：

- 「只登记不执行」会让 handler 白名单直接拒掉、触发即失败，`sys_task_log` 只剩失败记录，
  「还没做」与「做坏了」不可区分；
- 「先把它做出来」要预先猜未定稿的保留期 / 上传中记录口径，后续必然返工。

归口：审计日志归档 → 06_01 / 06_02 / 14；分片表预创建 → 13；软删除残留清理 → 13 回收站 / 14 归档。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.roots import BaseValueObject
from bms_core.jobs.client import JobInternalClient, build_service_client
from bms_core.servicecall.base import ServiceRequest
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
    "run_verify_audit_chain",
]

_HANDLER_MODULE = "bms_core.tasks.builtin"
"""内置执行体所在模块（handler 白名单前缀的唯一来源）。"""

FILE_SERVICE_KEY = "file"
"""文件服务标识（孤儿回收作业的提供方）。"""

PLATFORM_SERVICE_KEY = "platform"
"""平台服务标识（导出产物清理作业的提供方）。"""

REPORT_SERVICE_KEY = "report"
"""报表打印服务标识（打印产物清理作业的提供方）。"""

AUDIT_VERIFY_PATH = "/api/v1/platform/internal/audit/verify"
"""审计链校验内部端点（06_01，platform 服务）。"""

AUDIT_SHARD_ENSURE_PATH = "/api/v1/platform/internal/audit/shards/ensure"
"""审计分片预创建内部端点（06_01，platform 服务）。"""


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
            owner="06_01（审计日志分片）、13（其余分片表）",
            summary="提前创建下月分片表（sys_operation_log_yyyyMM 等）",
        ),
        BuiltinTaskSpec(
            code="verify_audit_chain",
            name="审计链校验",
            cron="30 5 * * *",
            handler=f"{_HANDLER_MODULE}:run_verify_audit_chain",
            owner="06_01（日志与审计）",
            summary="逐类校验审计日志哈希链（操作 / 登录），断裂即告警",
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


async def _post_platform(
    *, path: str, body: ConcurrentStableDict[str, object], ctx: TaskContext, label: str
) -> tuple[bool, str, ConcurrentStableDict[str, object]]:
    """调用 platform 内部端点（服务间调用）。

    Args:
        path: 目标路径（`/api/v1/...`）。
        body: JSON 请求体。
        ctx: 执行上下文（取租户主键）。
        label: 中文文案（用于失败消息）。

    Returns:
        tuple[bool, str, ConcurrentStableDict[str, object]]: （成功, 消息, data）。
    """
    try:
        client = build_service_client()
        response = await client.call(
            ServiceRequest(
                service=PLATFORM_SERVICE_KEY,
                method="POST",
                path=path,
                json_body=ConcurrentStableFrozenDict(dict(body)),
                tenant_id=None if ctx.run.tenant_id is None else str(ctx.run.tenant_id),
            )
        )
    except ServiceUnavailableError as exc:
        return False, f"{label}调用失败：{exc}", ConcurrentStableDict[str, object]()
    if response.status_code >= 400:
        return False, f"{label}调用失败：HTTP {response.status_code}", ConcurrentStableDict[str, object]()
    payload = response.payload()
    if not isinstance(payload, dict):
        return False, f"{label}响应非法（非 JSON 对象）", ConcurrentStableDict[str, object]()
    mapping = ConcurrentStableDict[str, object](cast("dict[str, object]", payload))
    if int(str(mapping.get("code", -1))) != 0:
        return False, f"{label}失败：{mapping.get('message') or mapping.get('code')}", mapping
    data = mapping.get("data")
    if not isinstance(data, dict):
        return True, "", ConcurrentStableDict[str, object]()
    return True, "", ConcurrentStableDict[str, object](cast("dict[str, object]", data))


async def run_precreate_shard_tables(ctx: TaskContext) -> TaskResult:
    """分片表预创建（触发型：审计日志分片，06_01）。

    Args:
        ctx: 执行上下文（本执行体只提交请求，建表 / 台账全在 platform 日志域）。

    Returns:
        TaskResult: 成功带创建月份；下游不可用为失败（由调度器按策略重试提交）。
    """
    ahead = get_settings().audit_log.precreate_months_ahead
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict({"months_ahead": ahead})
    ok, message, data = await _post_platform(path=AUDIT_SHARD_ENSURE_PATH, body=body, ctx=ctx, label="审计分片预创建")
    if not ok:
        return TaskResult.failed(message, output=message)
    months = data.get("months")
    return TaskResult.success("审计分片已预创建", output=f"months={months}")


async def run_verify_audit_chain(ctx: TaskContext) -> TaskResult:
    """审计链巡检（触发型：操作 + 登录两类日志，06_01）。

    Args:
        ctx: 执行上下文（本执行体只提交请求，逐条重算在 platform 日志域）。

    Returns:
        TaskResult: 全部通过为成功；任一断裂为失败（消息含断裂定位，接监控告警）。
    """
    checked: ConcurrentStableList[str] = ConcurrentStableList()
    for log_type in ("operation", "login"):
        body: ConcurrentStableDict[str, object] = ConcurrentStableDict({"log_type": log_type})
        ok, message, data = await _post_platform(
            path=AUDIT_VERIFY_PATH, body=body, ctx=ctx, label=f"审计链校验（{log_type}）"
        )
        if not ok:
            return TaskResult.failed(message, output=message)
        if not bool(data.get("valid", False)):
            broken = (
                f"month={data.get('broken_month')} index={data.get('broken_index')} "
                f"record_id={data.get('broken_record_id')}"
            )
            return TaskResult.failed(f"审计链断裂（{log_type}）：{broken}", output=broken)
        checked.add(f"{log_type}:{data.get('checked_records', 0)}")
    return TaskResult.success("审计链校验通过", output=";".join(checked))


async def run_purge_soft_deleted(ctx: TaskContext) -> TaskResult:
    """软删除残留物理清理（占位）。

    Args:
        ctx: 执行上下文。

    Returns:
        TaskResult: `skipped`（归口 13 回收站 / 14 归档）。
    """
    _ = ctx
    return _skipped("13（回收站）、14（归档）")
