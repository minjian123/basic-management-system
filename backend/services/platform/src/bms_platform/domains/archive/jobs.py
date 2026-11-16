"""归档域作业：归档执行与过期冷化文件清理。"""

from __future__ import annotations

from typing import cast

from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.plugin import resolve_plugin
from bms_core.db.engine import EngineFactory
from bms_core.db.keys import ARCHIVE_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.lock.base import BaseDistributedLock
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.services.executor import ArchiveExecutor

__all__ = ["ArchiveCleanupJob", "ArchiveRunJob", "reset_archive_registry"]

_registry_cache: EngineRegistry | None = None
"""懒建归档库引擎注册表（作业无请求态，与日志消费同口径）。"""


def _archive_registry() -> EngineRegistry:
    """取（懒建）归档库引擎注册表。

    Returns:
        EngineRegistry: 引擎注册表。
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = EngineRegistry(EngineFactory(get_settings()))
    return _registry_cache


def reset_archive_registry() -> None:
    """清空懒建注册表（测试隔离用）。"""
    global _registry_cache
    _registry_cache = None


class ArchiveRunJob(BaseJobHandler):
    """归档执行作业（扫描启用策略或指定策略）。"""

    job_type = "platform.archive.run"
    description = "执行归档策略（两段式 / 直冷 / 审计分片整月归档）"

    async def run(self, ctx: JobContext) -> JobResult:
        """执行归档。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功含执行摘要；失败可重试。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        policy_id = _optional_int(ctx.payload.get("policy_id"))
        policy_ids = ConcurrentStableList((policy_id,)) if policy_id is not None else None
        storage = _storage(settings)
        chain = _chain(settings)
        lock = _lock(settings)
        registry = _archive_registry()
        async with (
            ctx.session() as platform_session,
            session_scope(registry, db_key=ARCHIVE_DB_KEY) as archive_session,
        ):
            executor = ArchiveExecutor(
                cast("DbSession", platform_session),
                archive_session,
                settings=settings,
                storage=storage,
                chain=chain,
                lock=lock,
            )
            summary = await executor.run(
                policy_ids=policy_ids,
                operator_id=None,
                progress=ctx.report_progress,
                should_cancel=ctx.should_cancel,
            )
        failed = int(str(summary.get("failed", 0)))
        message = (
            f"归档完成：策略 {summary.get('policies', 0)} 条，归档 {summary.get('archived', 0)} 条，"
            f"冷化 {summary.get('cold', 0)} 条，失败 {failed} 条"
        )
        if failed:
            return JobResult.failed(message, retryable=True, output=summary)
        return JobResult.success(summary, message=message)


class ArchiveCleanupJob(BaseJobHandler):
    """过期冷化文件清理作业（按 `retention_until` 回销）。"""

    job_type = "platform.archive.cleanup"
    description = "清理过期归档冷化文件（数据 + 清单）并留痕"

    async def run(self, ctx: JobContext) -> JobResult:
        """执行清理。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功含清理条数。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        storage = _storage(settings)
        registry = _archive_registry()
        async with (
            ctx.session() as platform_session,
            session_scope(registry, db_key=ARCHIVE_DB_KEY) as archive_session,
        ):
            executor = ArchiveExecutor(
                cast("DbSession", platform_session),
                archive_session,
                settings=settings,
                storage=storage,
                chain=_chain(settings),
                lock=_lock(settings),
            )
            cleaned = await executor.cleanup()
        output: ConcurrentStableDict[str, object] = ConcurrentStableDict({"cleaned": cleaned})
        return JobResult.success(output, message=f"归档冷化文件清理完成：{cleaned} 个")


def _storage(settings: object) -> BaseObjectStorage:
    """解析对象存储实现。"""
    from bms_core.core.config import Settings

    resolved = cast("Settings", settings)
    return cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage",
            resolved.storage.provider or "null",
            expected_version=BaseObjectStorage.contract_version,
        ),
    )


def _chain(settings: object) -> BaseHashChain:
    """解析哈希链实现。"""
    from bms_core.core.config import Settings

    resolved = cast("Settings", settings)
    return cast(
        "BaseHashChain",
        resolve_plugin(
            "hash_chain",
            resolved.hash_chain.provider or Sha256HashChain.plugin_name,
            expected_version=BaseHashChain.contract_version,
        ),
    )


def _lock(settings: object) -> BaseDistributedLock:
    """解析分布式锁实现。"""
    from bms_core.core.config import Settings

    resolved = cast("Settings", settings)
    return cast(
        "BaseDistributedLock",
        resolve_plugin(
            "distributed_lock",
            resolved.distributed_lock.provider or "null",
            expected_version=BaseDistributedLock.contract_version,
        ),
    )


def _optional_int(value: object) -> int | None:
    """把负载值转为 int（None / 空串为空）。"""
    if value is None or value == "":
        return None
    return int(str(value))
