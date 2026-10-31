"""内置任务：清单登记 + 执行体（已落地的做真实动作，未落地的仍是占位）。

四条内置任务在 `sys_task` 里有定义（种子入库）、有 cron、有执行记录：

- **孤儿分片清理**（03_01 已落地）：执行体为**触发型**——经服务间调用驱动 file 服务的内部清理端点
  （扫描 / 清理 / 置 `orphan` 全在 file 域，基座不跨库写文件表），返回执行摘要；
- 其余三条仍是占位实现：返回 `skipped` 并在 `message` 里写明归口任务号。理由见详细设计 §4.6：

- 「只登记不执行」会让 handler 白名单直接拒掉、触发即失败，`sys_task_log` 只剩失败记录，
  「还没做」与「做坏了」不可区分；
- 「先把它做出来」要预先猜未定稿的保留期 / 上传中记录口径，后续必然返工。

归口：审计日志归档 → 06_01 / 06_02 / 14；分片表预创建 → 13；软删除残留清理 → 13 回收站 / 14 归档。
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import cast

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.plugin import build_plugin_registry, resolve_plugin
from bms_core.core.roots import BaseValueObject
from bms_core.servicecall.base import BaseServiceClient
from bms_core.storage.maintenance import FileMaintenanceClient
from bms_core.tasks.spec import TaskContext, TaskResult

__all__ = [
    "BUILTIN_TASK_SPECS",
    "BuiltinTaskSpec",
    "builtin_spec_of",
    "run_archive_audit_logs",
    "run_cleanup_orphan_parts",
    "run_precreate_shard_tables",
    "run_purge_soft_deleted",
]

_HANDLER_MODULE = "bms_core.tasks.builtin"
"""内置执行体所在模块（handler 白名单前缀的唯一来源）。"""


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
            owner="03_01（文件管理，已落地：触发 file 内部清理端点）",
            summary="回收上传中断遗留的分片对象与超期上传中记录",
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


def build_service_client() -> BaseServiceClient:
    """解析服务间调用客户端（离线执行体用：按 `[service_client].provider` 构建注册表）。

    Returns:
        BaseServiceClient: 调用客户端。

    Raises:
        ServiceUnavailableError: 未启用服务间调用实现（provider 为空）。
    """
    settings = get_settings()
    provider = settings.service_client.provider
    if not provider:
        raise ServiceUnavailableError("服务间调用实现未启用（[service_client].provider 为空）")
    for module in ("bms_core.servicecall.null", "bms_core.servicecall.http"):
        import_module(module)
    build_plugin_registry()
    return cast(
        "BaseServiceClient",
        resolve_plugin("service_client", provider, expected_version=BaseServiceClient.contract_version),
    )


async def run_cleanup_orphan_parts(ctx: TaskContext) -> TaskResult:
    """孤儿分片清理（触发型：经服务间调用驱动 file 服务的内部清理端点）。

    Args:
        ctx: 执行上下文（本执行体不读写任何库，只用 `sys_task_log` 记摘要）。

    Returns:
        TaskResult: 成功带回收摘要；下游不可用为失败（由调度器按策略重试）。
    """
    _ = ctx
    try:
        summary = await FileMaintenanceClient(build_service_client()).cleanup_orphans()
    except ServiceUnavailableError as exc:
        return TaskResult.failed(f"孤儿回收触发失败：{exc}")
    return TaskResult.success(
        f"孤儿回收完成：扫描 {summary.scanned} / 回收 {summary.orphaned} / 失败 {summary.failed}",
        output=f"scanned={summary.scanned} orphaned={summary.orphaned} failed={summary.failed}",
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
