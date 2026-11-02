"""导入作业处理器：`platform.import.execute`（异步执行与同步内联共用核心流程）。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import cast

from bms_core.audit.base import AuditCapturer
from bms_core.audit.null import NullAuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.config.http import HttpConfigSource
from bms_core.config.null import NullConfigSource
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import NotFoundError, ServiceUnavailableError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import resolve_plugin
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_core.jobs.client import build_service_client
from bms_core.jobs.plugins import ensure_job_plugins
from bms_core.outbox.store import SqlOutboxStore
from bms_core.password.default import DefaultPasswordPolicy
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.servicecall.base import BaseServiceClient
from bms_core.servicecall.null import NullServiceClient
from bms_core.storage.base import BaseObjectStorage
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_core.transfer.definition import (
    BaseImportDefinition,
    ImportBatchUnitOfWork,
    ImportDefinitionRegistry,
    ImportSummary,
)
from bms_core.transfer.importer import BaseImporter
from bms_core.transfer.limits import ImportLimits
from bms_core.transfer.openpyxl import OpenpyxlImporter
from bms_core.transfer.source import ImportSourceStore, ObjectStorageImportSourceStore
from bms_platform.domains.import_export.services.imports import JOB_TYPE, ImportExecutor
from bms_platform.imports import build_import_definitions

__all__ = ["ImportExecuteJob"]

_LOGGER = get_logger("bms")


class ImportExecuteJob(BaseJobHandler):
    """导入作业：读源文件 → 全量预检 → 全量原子写入 → 错误明细。"""

    job_type = JOB_TYPE
    description = "执行 Excel 批量导入（全量原子；错误明细写 sys_job_error）"

    def __init__(
        self,
        *,
        definitions_factory: Callable[..., ImportDefinitionRegistry] = build_import_definitions,
        importer: BaseImporter | None = None,
        source_store: ImportSourceStore | None = None,
        config: BaseConfigSource | None = None,
        audit: AuditCapturer | None = None,
        limits: ImportLimits | None = None,
    ) -> None:
        """初始化（测试可注入替身；生产按配置解析）。

        Args:
            definitions_factory: 定义装配函数（默认平台 users / roles）。
            importer: 导入器（None 按配置解析）。
            source_store: 源文件存储（None 按对象存储构造）。
            config: 系统参数取数（None 按配置解析）。
            audit: 审计捕获器（None 用占位）。
            limits: 生效参数（None 从参数源加载）。
        """
        self._definitions_factory = definitions_factory
        self._importer = importer
        self._source_store = source_store
        self._config = config
        self._audit = audit
        self._limits = limits

    async def run(self, ctx: JobContext) -> JobResult:
        """执行导入。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功 / 失败 / 取消。
        """
        settings = get_settings()
        ensure_job_plugins(settings)
        service_client = _service_client(settings)
        config = self._config if self._config is not None else _config_source(settings, service_client)
        audit = self._audit if self._audit is not None else NullAuditCapturer()
        limits = self._limits if self._limits is not None else await ImportLimits.load(config)
        importer = self._importer if self._importer is not None else OpenpyxlImporter()
        storage = _storage(settings)
        source_store = self._source_store if self._source_store is not None else ObjectStorageImportSourceStore(storage)
        hasher = _hasher(settings)
        policy = DefaultPasswordPolicy(config=config, hasher=hasher)
        outbox = SqlOutboxStore()
        definitions = self._definitions_factory(
            hasher=hasher,
            policy=policy,
            outbox=outbox,
            service_client=service_client,
            audit=audit,
            config=config,
        )
        tenant_code = str(ctx.payload.get("tenant_code") or "") or None
        quota = TenantQuotaClient(
            service_client,
            tenant_id=None if ctx.tenant_id is None else str(ctx.tenant_id),
            tenant_code=tenant_code,
        )
        executor = ImportExecutor(
            definitions=definitions,
            importer=importer,
            limits=limits,
            config=config,
            audit=audit,
            quota=quota,
        )
        biz = str(ctx.payload.get("biz") or "")
        definition = executor.definition(biz)
        source_key = str(ctx.payload.get("source_key") or "")
        actor_raw = ctx.payload.get("actor")
        actor = int(str(actor_raw)) if actor_raw not in (None, "") else None
        try:
            data = await source_store.get(source_key)
        except (NotFoundError, ServiceUnavailableError, OSError) as exc:
            return JobResult.failed(f"导入源文件不存在或不可读：{exc}", retryable=False)
        try:
            return await _run(ctx, executor, definition, data, actor, tenant_code)
        finally:
            with contextlib.suppress(Exception):
                await source_store.delete(source_key)


async def _run(
    ctx: JobContext,
    executor: ImportExecutor,
    definition: BaseImportDefinition,
    data: bytes,
    actor: int | None,
    tenant_code: str | None,
) -> JobResult:
    """执行核心流程（拆方法便于测试）。"""
    async with ctx.session() as session:
        rows = await executor.parse(data, definition=definition)
        valid, errors = await executor.validate(definition, rows, session=session)
        error_rows = len({error.row for error in errors})
        if errors:
            for error in errors:
                await ctx.add_error(error.message, row_no=error.row, column_key=error.field)
            summary = ImportSummary(
                total=len(rows),
                success_count=0,
                fail_count=error_rows,
                blocked_count=max(len(rows) - error_rows, 0),
                committed=False,
            )
            return JobResult.failed("存在非法行，整批未导入", retryable=False, output=summary.to_output())
        try:
            # 外层必有事务（同步 = 调用方请求事务；异步 = 作业执行事务）：批次用 savepoint 保证
            # 「任一行失败整批回滚」且作业记录 / 错误明细不受影响。
            async with session.begin_nested():
                await executor.write(
                    definition,
                    valid,
                    session=session,
                    uow=ImportBatchUnitOfWork(session),
                    actor=actor,
                    tenant_id=ctx.tenant_id,
                    tenant_code=tenant_code,
                    job_ctx=ctx,
                )
        except asyncio.CancelledError:
            return JobResult.canceled("导入已取消")
        except Exception as exc:  # 整批回滚；不可重试
            _LOGGER.warning("导入整批写入失败", error=str(exc), error_type=type(exc).__name__)
            await ctx.add_error(f"整批写入失败：{exc}", item_ref="batch")
            summary = ImportSummary(
                total=len(rows),
                success_count=0,
                fail_count=0,
                blocked_count=len(rows),
                committed=False,
            )
            return JobResult.failed("整批写入失败，已回滚", retryable=False, output=summary.to_output())
        summary = ImportSummary(
            total=len(rows),
            success_count=len(valid),
            fail_count=0,
            blocked_count=0,
            committed=True,
        )
        await ctx.report_progress(len(rows), len(rows))
        return JobResult.success(summary.to_output(), message=f"导入完成：{len(valid)} 行")


def _service_client(settings: Settings) -> BaseServiceClient:
    """解析服务间客户端（未启用用空实现）。"""
    try:
        return build_service_client()
    except ServiceUnavailableError:
        return NullServiceClient()


def _config_source(settings: Settings, service_client: BaseServiceClient) -> BaseConfigSource:
    """解析参数取数：优先 HTTP（worker 无请求库会话），不可用回落占位。"""
    if isinstance(service_client, NullServiceClient):
        return NullConfigSource()
    return HttpConfigSource(client=service_client)


def _hasher(settings: Settings) -> Pbkdf2PasswordHasher:
    """解析口令哈希（缺省 PBKDF2）。"""
    options = settings.password_hasher.options
    iterations = int(str(options.get("iterations") or 600000))
    return Pbkdf2PasswordHasher(iterations=iterations)


def _storage(settings: Settings) -> BaseObjectStorage:
    """解析对象存储实现。"""
    return cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage", settings.storage.provider, expected_version=BaseObjectStorage.contract_version
        ),
    )
