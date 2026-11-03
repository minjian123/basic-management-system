"""报表域作业：单据打印产物过期清理（`print.artifact.cleanup`，04_03）。

- **判据**：`print.artifact_ttl` 之前完成、成功终态的 `print.batch.execute` 作业；
- **口径**：只回销作业结果里的 `items[].object_key`——同步单条 / 同步批量打印不写作业记录，
  本次不覆盖（产物 key 按「模板 + 单据」去重，堆积上界为单据数 × 模板数）；
- **覆盖防护**：打印产物 key 固定（重打覆盖同一 key），删前反查同库是否存在更晚的成功打印作业
  引用同一 key，有则跳过且不标记（宁可不删，不可误删）；
- **幂等**：对象删除自身幂等；已标记 `expired_at` 的作业直接跳过；
- **失败**：首条删除失败立即抛出、整作业失败（不留「部分成功」模糊态），`max_attempts=1` 不自动重跑。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.config.base import BaseConfigSource
from bms_core.config.http import HttpConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.session import DbSession
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.client import build_service_client
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.print.limits import PrintLimits
from bms_core.servicecall.base import BaseServiceClient
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.base import BaseObjectStorage
from bms_report.domains.report.repositories.job import JobArtifact, PrintJobRepository

__all__ = ["JOB_TYPE", "SOURCE_JOB_TYPE", "PrintArtifactCleanupJob"]

_LOGGER = get_logger("bms")

JOB_TYPE = "print.artifact.cleanup"
"""打印产物过期清理作业类型。"""

SOURCE_JOB_TYPE = "print.batch.execute"
"""产物来源作业类型（其 `result.items[].object_key` 是本作业的清理对象）。"""


class PrintArtifactCleanupJob(BaseJobHandler):
    """单据打印产物过期清理：按作业结果里的产物 key 回销对象（幂等 + 覆盖防护）。"""

    job_type = JOB_TYPE
    description = "清理过期单据打印产物（按 print.artifact_ttl 与作业结果里的对象 key）"

    def __init__(
        self,
        *,
        storage: BaseObjectStorage | None = None,
        limits: PrintLimits | None = None,
    ) -> None:
        """初始化。

        Args:
            storage: 对象存储实现（None 按配置解析）。
            limits: 生效参数（None 从参数源加载）。
        """
        self._storage = storage
        self._limits = limits

    async def run(self, ctx: JobContext) -> JobResult:
        """执行清理（分批读取 → 覆盖判定 → 删对象 → 单独事务标记）。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功（扫描 / 清理 / 跳过 / 标记条数）。

        Raises:
            Exception: 任一对象删除失败（整作业失败，由执行器落 failed 终态）。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        limits = self._limits if self._limits is not None else await PrintLimits.load(_config_source())
        storage = self._storage if self._storage is not None else _storage(settings)
        before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=limits.artifact_ttl)
        scanned = 0
        cleaned = 0
        skipped = 0
        marked = 0
        offset = 0
        batch_size = limits.cleanup_batch_size
        while True:
            batch = await _batch(ctx, before, limit=batch_size, offset=offset)
            if not batch:
                break
            offset += batch_size
            for item in batch:
                if item.expired:
                    skipped += 1
                    continue
                scanned += 1
                blocked = await _blocked_keys(ctx, item.object_keys, after_job_id=item.job_id)
                skipped += len(blocked)
                for key in item.object_keys:
                    if key in blocked:
                        continue
                    try:
                        await storage.delete(key)
                    except Exception as exc:
                        _LOGGER.warning("打印产物清理失败", job_id=item.job_id, object_key=key, error=str(exc))
                        raise
                    cleaned += 1
                # 有 key 被更晚作业引用时不标记：对象已属于更新的产物，下轮仍需再判
                if not blocked and await _mark(ctx, item.job_id):
                    marked += 1
            await ctx.report_progress(scanned, None)
            if await ctx.should_cancel():
                break
        return JobResult.success(
            ConcurrentStableDict({"scanned": scanned, "cleaned": cleaned, "skipped": skipped, "marked": marked}),
            message=f"打印产物清理完成：扫描 {scanned} / 清理 {cleaned} / 跳过 {skipped} / 标记 {marked}",
        )


async def _batch(
    ctx: JobContext,
    before: datetime,
    *,
    limit: int,
    offset: int,
) -> ConcurrentStableList[JobArtifact]:
    """取一批过期打印作业的产物快照（事务内取值到不可变对象）。

    Args:
        ctx: 作业上下文。
        before: 完成时间上界。
        limit: 单批上限。
        offset: 偏移。

    Returns:
        ConcurrentStableList[JobArtifact]: 批内作业产物快照。
    """
    async with ctx.session() as raw:
        session = cast("DbSession", raw)
        async with session.begin():
            return await PrintJobRepository(session).list_succeeded_before(
                SOURCE_JOB_TYPE, before, limit=limit, offset=offset
            )


async def _blocked_keys(
    ctx: JobContext,
    keys: ConcurrentStableList[str],
    *,
    after_job_id: int,
) -> ConcurrentStableSet[str]:
    """判定哪些 key 被更晚的成功打印作业引用（同一事务内判完，避免逐 key 开事务）。

    Args:
        ctx: 作业上下文。
        keys: 本作业记录的产物 key。
        after_job_id: 基准作业主键。

    Returns:
        ConcurrentStableSet[str]: 不可删除的 key 集合（空集合表示可全删）。
    """
    blocked: ConcurrentStableSet[str] = ConcurrentStableSet()
    if not keys:
        return blocked
    async with ctx.session() as raw:
        session = cast("DbSession", raw)
        async with session.begin():
            repository = PrintJobRepository(session)
            for key in keys:
                if await repository.has_newer_reference(SOURCE_JOB_TYPE, key, after_job_id=after_job_id):
                    blocked.add(key)
    return blocked


async def _mark(ctx: JobContext, job_id: int) -> bool:
    """把 `expired_at` 写入作业结果（保留原 key 便于审计；已标记不重复写）。

    Args:
        ctx: 作业上下文。
        job_id: 作业主键。

    Returns:
        bool: 本次写入返回 True。
    """
    async with ctx.session() as raw:
        session = cast("DbSession", raw)
        async with session.begin():
            return await PrintJobRepository(session).mark_expired(job_id)


def _service_client() -> BaseServiceClient:
    """解析服务间客户端（未启用用空实现）。

    Returns:
        BaseServiceClient: 调用客户端。
    """
    try:
        return build_service_client()
    except ServiceUnavailableError:
        return NullServiceClient()


def _config_source() -> BaseConfigSource:
    """解析参数取数（worker 无请求库会话，优先 HTTP，不可用回落占位）。

    Returns:
        BaseConfigSource: 参数源。
    """
    client = _service_client()
    if isinstance(client, NullServiceClient):
        return NullConfigSource()
    return HttpConfigSource(client=client)


def _storage(settings: Settings) -> BaseObjectStorage:
    """解析对象存储实现。

    Args:
        settings: 应用配置。

    Returns:
        BaseObjectStorage: 对象存储实例。
    """
    return cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage", settings.storage.provider, expected_version=BaseObjectStorage.contract_version
        ),
    )
