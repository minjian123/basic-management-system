"""导出域作业：异步导出执行（`platform.export.execute`）与产物过期清理（`platform.export.cleanup`）。

- 执行作业：读负载（明文权限在提交时已固化）→ 同源取数 → 脱敏 → 生成产物 → 落对象存储 →
  结果摘要写 `sys_job.result`（供状态端点取址与清理作业回销）。
- 清理作业：按 `export.artifact_ttl` 取「成功终态且完成时间早于阈值」的导出作业，删除 `result` 里记录的
  产物对象并在 `result` 追加 `expired_at`（保留 key 便于审计）；对象存储契约无 `list`，故按作业记录回销。
- 取消：取数批次边界检查 `ctx.should_cancel()`，命中抛 `CancelledError` 由执行器转 `canceled` 终态。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from bms_core.config.base import BaseConfigSource
from bms_core.config.http import HttpConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.db.session import DbSession
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.client import build_service_client
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.print.base import BasePrintExporter
from bms_core.servicecall.base import BaseServiceClient
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.base import BaseObjectStorage
from bms_core.transfer.artifacts import ExportArtifactStore, ObjectStorageExportArtifactStore
from bms_core.transfer.export_definition import ExportDefinitionRegistry
from bms_core.transfer.export_limits import ExportLimits
from bms_core.transfer.exporter import BaseExporter
from bms_platform.domains.import_export.repositories.job import ImportJobRepository
from bms_platform.domains.import_export.services.exports import (
    CLEANUP_JOB_TYPE,
    JOB_TYPE,
    ExportExecutor,
    ExportPayload,
    build_export_masker,
    cleanup_targets,
)
from bms_platform.exports import build_export_definitions

__all__ = ["ExportCleanupJob", "ExportExecuteJob"]

_LOGGER = get_logger("bms")

_EXPIRED_FIELD = "expired_at"
"""`sys_job.result` 里表示「产物已清理」的时间字段。"""


class ExportExecuteJob(BaseJobHandler):
    """异步导出作业：取数 → 脱敏 → 生成产物 → 落存储。"""

    job_type = JOB_TYPE
    description = "执行列表导出（Excel / 列表 PDF），产物落对象存储并记入作业结果"

    def __init__(
        self,
        *,
        definitions_factory: Callable[[], ExportDefinitionRegistry] = build_export_definitions,
        excel_exporter: BaseExporter | None = None,
        print_exporter: BasePrintExporter | None = None,
        artifacts: ExportArtifactStore | None = None,
        limits: ExportLimits | None = None,
    ) -> None:
        """初始化（测试可注入替身；生产按配置解析）。

        Args:
            definitions_factory: 定义装配函数（默认平台 users / roles）。
            excel_exporter: Excel 导出器（None 按配置解析）。
            print_exporter: 打印导出（None 按配置解析）。
            artifacts: 产物存储端口（None 按对象存储构造）。
            limits: 生效参数（None 从参数源加载）。
        """
        self._definitions_factory = definitions_factory
        self._excel_exporter = excel_exporter
        self._print_exporter = print_exporter
        self._artifacts = artifacts
        self._limits = limits

    async def run(self, ctx: JobContext) -> JobResult:
        """执行异步导出。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功（产物摘要 + 条数）/ 取消。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        payload = ExportPayload.from_job_payload(ctx.payload)
        limits = self._limits if self._limits is not None else await ExportLimits.load(_config_source())
        executor = ExportExecutor(
            definitions=self._definitions_factory(),
            excel_exporter=self._excel_exporter if self._excel_exporter is not None else _excel_exporter(settings),
            print_exporter=(self._print_exporter if self._print_exporter is not None else _print_exporter(settings)),
            artifacts=self._artifacts if self._artifacts is not None else _artifacts(settings),
            limits=limits,
        )
        masker = build_export_masker(settings, payload.plain)

        async def progress(done: int, total: int) -> None:
            """批次边界上报进度并检查取消。

            Args:
                done: 已完成条数。
                total: 总条数。

            Raises:
                CancelledError: 已请求取消。
            """
            if await ctx.should_cancel():
                raise asyncio.CancelledError
            await ctx.report_progress(done, total)

        try:
            async with ctx.session() as session:
                artifact, total = await executor.execute_and_store(
                    cast("DbSession", session), payload, masker=masker, progress=progress
                )
        except asyncio.CancelledError:
            return JobResult.canceled("导出已取消")
        output = ConcurrentStableDict(artifact.to_result())
        output.set("total", total)
        return JobResult.success(output, message=f"导出完成：{total} 条")


class ExportCleanupJob(BaseJobHandler):
    """导出产物过期清理：按作业结果里的产物 key 回销对象（幂等）。"""

    job_type = CLEANUP_JOB_TYPE
    description = "清理过期导出产物（按 export.artifact_ttl 与作业结果里的对象 key）"

    def __init__(
        self,
        *,
        artifacts: ExportArtifactStore | None = None,
        limits: ExportLimits | None = None,
    ) -> None:
        """初始化。

        Args:
            artifacts: 产物存储端口（None 按对象存储构造）。
            limits: 生效参数（None 从参数源加载）。
        """
        self._artifacts = artifacts
        self._limits = limits

    async def run(self, ctx: JobContext) -> JobResult:
        """执行清理（按批读取 → 删对象 → 单独事务标记）。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功（扫描 / 清理 / 失败条数）。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        limits = self._limits if self._limits is not None else await ExportLimits.load(_config_source())
        artifacts = self._artifacts if self._artifacts is not None else _artifacts(settings)
        before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=limits.artifact_ttl)
        scanned = 0
        cleaned = 0
        failed = 0
        offset = 0
        batch_size = limits.fetch_batch_size
        while True:
            batch = await _expired_batch(ctx, before, limit=batch_size, offset=offset)
            if not batch:
                break
            offset += batch_size
            marked: list[int] = []
            for job_id, key, expired in batch:
                if expired:
                    continue
                scanned += 1
                if key:
                    try:
                        await artifacts.delete(key)
                        cleaned += 1
                    except Exception as exc:  # 单条失败不阻断整批（幂等，下轮再试）
                        failed += 1
                        _LOGGER.warning("导出产物清理失败", object_key=key, error=str(exc))
                        continue
                marked.append(job_id)
            await _mark_expired(ctx, marked)
            await ctx.report_progress(scanned, None)
            if await ctx.should_cancel():
                break
        return JobResult.success(
            ConcurrentStableDict({"scanned": scanned, "cleaned": cleaned, "failed": failed}),
            message=f"导出产物清理完成：扫描 {scanned} / 清理 {cleaned} / 失败 {failed}",
        )


async def _expired_batch(
    ctx: JobContext,
    before: datetime,
    *,
    limit: int,
    offset: int,
) -> list[tuple[int, str | None, bool]]:
    """取一批过期导出作业的 `(主键, 产物 key, 是否已标记)`（事务内取值到局部，避免事务后读 ORM 属性）。

    Args:
        ctx: 作业上下文。
        before: 完成时间上界。
        limit: 单批上限。
        offset: 偏移。

    Returns:
        list[tuple[int, str | None, bool]]: 批内作业、产物 key 与已标记状态。
    """
    async with ctx.session() as raw:
        session = cast("DbSession", raw)
        async with session.begin():
            rows = await ImportJobRepository(session).list_succeeded_before(
                JOB_TYPE, before, limit=limit, offset=offset
            )
            return [(int(row.id), cleanup_targets(row.result), _is_expired(row.result)) for row in rows]


async def _mark_expired(ctx: JobContext, job_ids: list[int]) -> None:
    """把 `expired_at` 写入作业结果（保留原 key 便于审计；已标记的跳过）。

    Args:
        ctx: 作业上下文。
        job_ids: 已处理作业主键。
    """
    if not job_ids:
        return
    async with ctx.session() as raw:
        session = cast("DbSession", raw)
        async with session.begin():
            repository = ImportJobRepository(session)
            for job_id in job_ids:
                record = await repository.get(job_id)
                if record is None:
                    continue
                record.result = _with_expired(record.result)


def _is_expired(raw: str | None) -> bool:
    """结果里是否已标记 `expired_at`。

    Args:
        raw: 结果文本。

    Returns:
        bool: 已标记为 True。
    """
    if not raw:
        return False
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(loaded, dict) and bool(cast("dict[str, object]", loaded).get(_EXPIRED_FIELD))


def _with_expired(raw: str | None) -> str:
    """在结果 JSON 上追加 `expired_at`（已存在原样返回）。

    Args:
        raw: 原结果文本。

    Returns:
        str: 新结果文本。
    """
    parsed: dict[str, object] = {}
    if raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            parsed = cast("dict[str, object]", loaded)
    if parsed.get(_EXPIRED_FIELD):
        return raw or "{}"
    parsed[_EXPIRED_FIELD] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return json.dumps(parsed, ensure_ascii=False)


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


def _artifacts(settings: Settings) -> ExportArtifactStore:
    """解析产物存储端口（worker 进程按需装配插件）。

    Args:
        settings: 应用配置。

    Returns:
        ExportArtifactStore: 产物存储端口。
    """
    storage = cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage", settings.storage.provider, expected_version=BaseObjectStorage.contract_version
        ),
    )
    return ObjectStorageExportArtifactStore(storage)


def _excel_exporter(settings: Settings) -> BaseExporter:
    """解析 Excel 导出器。

    Args:
        settings: 应用配置。

    Returns:
        BaseExporter: 导出器实例。
    """
    return cast(
        "BaseExporter",
        resolve_plugin("exporter", settings.exporter.provider, expected_version=BaseExporter.contract_version),
    )


def _print_exporter(settings: Settings) -> BasePrintExporter:
    """解析打印导出（列表 PDF）。

    Args:
        settings: 应用配置。

    Returns:
        BasePrintExporter: 打印导出实例。
    """
    return cast(
        "BasePrintExporter",
        resolve_plugin(
            "print_exporter", settings.print_exporter.provider, expected_version=BasePrintExporter.contract_version
        ),
    )
