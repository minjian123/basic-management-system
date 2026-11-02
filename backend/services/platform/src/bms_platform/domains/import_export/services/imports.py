"""导入编排：文件检查 / 同步内联 / 异步提交 / 幂等 / 状态 / 错误明细。"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Callable, Mapping
from typing import cast

from bms_core.audit.base import AuditCapturer
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConflictError,
    ImportBizNotRegisteredError,
    ImportFileInvalidError,
    ImportFileTooLargeError,
    ImportIdempotencyRequiredError,
    ImportReportNotFoundError,
    ImportReportNotReadyError,
    ImportRowLimitExceededError,
    ImportTemplateMismatchError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IdempotencyStore, build_idempotency_key
from bms_core.jobs.base import JobContext, JobResult
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission
from bms_core.models.job import JOB_TERMINAL_STATUSES, SysJob
from bms_core.permission.base import BasePermissionChecker
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_core.transfer.definition import (
    BaseImportDefinition,
    ImportDefinitionRegistry,
    ImportRowContext,
    ImportSummary,
)
from bms_core.transfer.importer import BaseImporter, ParsedRow, RowError
from bms_core.transfer.limits import ImportLimits
from bms_core.transfer.openpyxl_io import (
    XlsxInvalidFileError,
    XlsxTemplateMismatchError,
    build_error_report,
    build_template,
)
from bms_core.transfer.source import ImportSourceStore, build_import_source_key
from bms_platform.domains.import_export.repositories.job import ImportJobRepository
from bms_platform.domains.import_export.schemas.imports import ImportExecuteResult, ImportJobStatus
from bms_platform.domains.import_export.services.report import (
    build_error_items,
    parse_job_result,
    report_filename,
    report_key,
    token_payload,
)

__all__ = ["JOB_TYPE", "ImportExecutor", "ImportService"]

JOB_TYPE = "platform.import.execute"
"""导入作业类型（与 `[[jobs]]` 声明一致）。"""

_SYNC_ERROR_LIMIT = 200
"""同步响应 / 幂等首次结果携带的错误条数上限。"""

_LOGGER = get_logger("bms")


class ImportExecutor(BaseFrameworkObject):
    """导入核心流程：定义解析 → 解析文件 → 全量预检 → 全量原子写入。"""

    def __init__(
        self,
        *,
        definitions: ImportDefinitionRegistry,
        importer: BaseImporter,
        limits: ImportLimits,
        config: BaseConfigSource | None,
        audit: AuditCapturer | None,
        quota: TenantQuotaClient | None,
    ) -> None:
        """初始化。

        Args:
            definitions: 业务定义注册表。
            importer: 导入器（真实 openpyxl）。
            limits: 生效参数。
            config: 系统参数取数。
            audit: 审计捕获器。
            quota: 租户配额客户端（可为 None）。
        """
        self._definitions = definitions
        self._importer = importer
        self._limits = limits
        self._config = config
        self._audit = audit
        self._quota = quota

    def definition(self, biz: str) -> BaseImportDefinition:
        """按业务标识取定义。

        Args:
            biz: 业务标识。

        Returns:
            BaseImportDefinition: 导入定义。

        Raises:
            ImportBizNotRegisteredError: 未注册（`50307`）。
        """
        definition = self._definitions.get(biz)
        if definition is None:
            raise ImportBizNotRegisteredError(f"导入业务未注册：{biz}")
        return definition

    async def parse(self, data: bytes, *, definition: BaseImportDefinition) -> ConcurrentStableList[ParsedRow]:
        """解析文件并校验行数上限。

        Args:
            data: 文件字节。
            definition: 业务定义。

        Returns:
            ConcurrentStableList[ParsedRow]: 数据行。

        Raises:
            ImportRowLimitExceededError: 数据行数超限（`50304`）。
            ImportFileInvalidError: 文件非法 / 无数据行（`50302`）。
            ImportTemplateMismatchError: sheet 缺失 / 表头不匹配（`50301`）。
        """
        try:
            rows = await self._importer.parse_rows(data, columns=definition.columns)
        except XlsxTemplateMismatchError as exc:
            raise ImportTemplateMismatchError(str(exc)) from exc
        except XlsxInvalidFileError as exc:
            raise ImportFileInvalidError(str(exc)) from exc
        if len(rows) > self._limits.max_rows:
            raise ImportRowLimitExceededError(f"数据行数超限（{len(rows)} > {self._limits.max_rows}）")
        return rows

    async def validate(
        self, definition: BaseImportDefinition, rows: ConcurrentStableList[ParsedRow], *, session: DbSession
    ) -> tuple[ConcurrentStableList[ParsedRow], ConcurrentStableList[RowError]]:
        """全量预检（业务定义逐行校验）。

        Args:
            definition: 业务定义。
            rows: 解析行。
            session: 当前会话（定义预取库内键）。

        Returns:
            tuple: （合法行, 全部行错误）。
        """
        preloaded = await definition.preload(session, rows)
        valid: ConcurrentStableList[ParsedRow] = ConcurrentStableList()
        errors: ConcurrentStableList[RowError] = ConcurrentStableList()
        generic = await self._importer.validate_rows(rows, columns=definition.columns)
        for error in generic.errors:
            errors.add(error)
        for row in generic.valid_rows:
            row_errors = await definition.validate_row(row, preloaded, config=self._config)
            if row_errors:
                for error in row_errors:
                    errors.add(error)
                continue
            valid.add(row)
        return valid, errors

    async def write(
        self,
        definition: BaseImportDefinition,
        rows: ConcurrentStableList[ParsedRow],
        *,
        session: DbSession,
        uow: UnitOfWork,
        actor: int | None,
        tenant_id: int | None,
        tenant_code: str | None,
        job_ctx: JobContext | None = None,
    ) -> None:
        """全量原子写入（调用方负责事务 / savepoint）。

        Args:
            definition: 业务定义。
            rows: 合法行（已通过全量预检）。
            session: 当前会话。
            uow: 当前工作单元。
            actor: 操作人。
            tenant_id: 租户主键。
            tenant_code: 租户编码。
            job_ctx: 异步作业上下文（同步内联为 None）。

        Raises:
            asyncio.CancelledError: 批次边界发现取消。
            Exception: 任一行业务失败（调用方回滚整批）。
        """
        ctx = ImportRowContext(
            session=session,
            uow=uow,
            actor=actor,
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            audit=self._audit,
            quota=self._quota,
            job_ctx=job_ctx,
            config=self._config,
        )
        quota_key = definition.quota_key
        if quota_key is not None and self._quota is not None:
            await self._quota.consume(quota_key, len(rows), ref=f"import:{definition.biz}")
        try:
            for index, row in enumerate(rows, start=1):
                await definition.write_row(row, ctx)
                if job_ctx is not None and index % self._limits.batch_size == 0:
                    if await job_ctx.should_cancel():
                        raise asyncio.CancelledError()
                    await job_ctx.report_progress(index, len(rows))
        except BaseException:
            if quota_key is not None and self._quota is not None:
                await self._quota.release(quota_key, len(rows))
            raise


class ImportService(BaseFrameworkObject):
    """API 侧导入编排：模板 / 执行 / 状态 / 错误明细。"""

    def __init__(
        self,
        *,
        executor: ImportExecutor,
        source_store: ImportSourceStore,
        idempotency: IdempotencyStore,
        runner_factory: Callable[[], JobRunner],
        cache: CacheRegion,
        limits: ImportLimits,
        checker: BasePermissionChecker | None = None,
    ) -> None:
        """初始化。

        Args:
            executor: 导入核心流程。
            source_store: 源文件存储。
            idempotency: 幂等存储。
            runner_factory: 作业提交器工厂（零参调用返回 `JobRunner`）。
            cache: 缓存域（report token 映射）。
            limits: 生效参数。
            checker: 权限校验器（定义业务写权限）。
        """
        self._executor = executor
        self._source_store = source_store
        self._idempotency = idempotency
        self._runner_factory = runner_factory
        self._cache = cache
        self._limits = limits
        self._checker = checker

    def template(self, biz: str) -> tuple[bytes, str]:
        """生成模板。

        Args:
            biz: 业务标识。

        Returns:
            tuple[bytes, str]: （xlsx 字节, 文件名）。

        Raises:
            ImportBizNotRegisteredError: 未注册（`50307`）。
        """
        definition = self._executor.definition(biz)
        return build_template(definition.columns), f"{definition.title}-导入模板.xlsx"

    async def execute(
        self,
        *,
        biz: str,
        data: bytes,
        file_name: str,
        idem_key: str | None,
        uow: UnitOfWork,
        tenant_id: int | None,
        tenant_code: str | None,
        actor: int | None,
        db_key: str,
    ) -> ImportExecuteResult:
        """执行导入（同步内联 / 异步作业 / 幂等命中）。

        Args:
            biz: 业务标识。
            data: 文件字节。
            file_name: 原始文件名。
            idem_key: `Idempotency-Key` 请求头。
            uow: 请求级工作单元。
            tenant_id: 租户主键。
            tenant_code: 租户编码。
            actor: 操作人。
            db_key: 租户库键（内联作业上下文）。

        Returns:
            ImportExecuteResult: 执行结果。

        Raises:
            ImportIdempotencyRequiredError: 缺少幂等键（`50305`）。
            ImportFileTooLargeError: 文件超限（`50303`）。
            ImportBizNotRegisteredError: 业务未注册（`50307`）。
            PermissionError: 缺少业务写权限（`30001`）。
        """
        if not idem_key or not idem_key.strip():
            raise ImportIdempotencyRequiredError("缺少 Idempotency-Key")
        if not file_name.lower().endswith(".xlsx"):
            raise ImportFileInvalidError("仅支持 .xlsx 文件")
        idem_scope = _idem_scope(biz, idem_key)
        redis_key = build_idempotency_key(key=idem_scope, tenant=_tenant_str(tenant_id))
        if not await self._idempotency.begin(redis_key):
            cached = await self._idempotency.load(redis_key)
            if cached is None:
                raise ConflictError("同一幂等键的请求正在处理中，请稍后重试")
            return ImportExecuteResult.model_validate({**cached, "duplicate": True})
        definition = self._executor.definition(biz)
        if definition.write_permission is not None and self._checker is not None:
            self._checker.require(definition.write_permission)
        if len(data) > self._limits.max_size:
            raise ImportFileTooLargeError(f"文件大小超限（>{self._limits.max_size} 字节）")
        token = secrets.token_urlsafe(24)
        source_key = build_import_source_key(tenant_code, token)
        try:
            rows = await self._executor.parse(data, definition=definition)
            await self._source_store.put(source_key, data)
            if len(rows) <= self._limits.sync_max_rows:
                result = await self._execute_inline(
                    biz=biz,
                    source_key=source_key,
                    file_name=file_name,
                    file_size=len(data),
                    total_rows=len(rows),
                    token=token,
                    idem_scope=idem_scope,
                    uow=uow,
                    tenant_id=tenant_id,
                    tenant_code=tenant_code,
                    actor=actor,
                    db_key=db_key,
                )
            else:
                result = await self._submit_async(
                    biz=biz,
                    source_key=source_key,
                    file_name=file_name,
                    file_size=len(data),
                    total_rows=len(rows),
                    token=token,
                    idem_scope=idem_scope,
                    uow=uow,
                    tenant_id=tenant_id,
                    tenant_code=tenant_code,
                    actor=actor,
                )
            await self._idempotency.save(redis_key, result.model_dump(by_alias=True, mode="json"))
            return result
        except BaseException:
            await _safe_delete(self._source_store, source_key)
            await _safe_release(self._idempotency, redis_key)
            raise

    async def _execute_inline(
        self,
        *,
        biz: str,
        source_key: str,
        file_name: str,
        file_size: int,
        total_rows: int,
        token: str,
        idem_scope: str,
        uow: UnitOfWork,
        tenant_id: int | None,
        tenant_code: str | None,
        actor: int | None,
        db_key: str,
    ) -> ImportExecuteResult:
        """同步内联执行。"""
        payload = _job_payload(biz, source_key, file_name, file_size, total_rows, actor, tenant_code, token)
        submission = JobSubmission(
            job_type=JOB_TYPE,
            payload=payload,
            idempotency_key=idem_scope,
            max_attempts=1,
        )
        try:
            async with uow.begin():
                session = cast("DbSession", uow.session)
                record, job_result = await _runner(self._runner_factory).run_inline(
                    session, submission, db_key=db_key, tenant_id=tenant_id
                )
            session = cast("DbSession", uow.session)
            repository = ImportJobRepository(session)
            errors_count = await repository.count_errors(int(record.id))
            errors = await repository.list_errors(int(record.id), limit=_SYNC_ERROR_LIMIT)
            summary = _summary_of(job_result, total_rows, errors_count)
            if summary.fail_count > 0:
                await self._cache.aset(
                    report_key(self._cache, tenant_code, token),
                    token_payload(int(record.id), biz),
                    ttl=self._limits.error_report_ttl,
                )
            return ImportExecuteResult.model_validate(
                {
                    "total": summary.total,
                    "success_count": summary.success_count,
                    "fail_count": summary.fail_count,
                    "blocked_count": summary.blocked_count,
                    "committed": summary.committed,
                    "errors": build_error_items(errors),
                    "async": False,
                    "job_id": int(record.id),
                    "report_token": token if summary.fail_count > 0 else None,
                    "duplicate": False,
                }
            )
        finally:
            await _safe_delete(self._source_store, source_key)

    async def _submit_async(
        self,
        *,
        biz: str,
        source_key: str,
        file_name: str,
        file_size: int,
        total_rows: int,
        token: str,
        idem_scope: str,
        uow: UnitOfWork,
        tenant_id: int | None,
        tenant_code: str | None,
        actor: int | None,
    ) -> ImportExecuteResult:
        """提交异步作业。"""
        payload = _job_payload(biz, source_key, file_name, file_size, total_rows, actor, tenant_code, token)
        submission = JobSubmission(
            job_type=JOB_TYPE,
            payload=payload,
            idempotency_key=idem_scope,
            max_attempts=1,
        )
        async with uow.begin():
            record = await _runner(self._runner_factory).submit(
                cast("DbSession", uow.session), submission, tenant_id=tenant_id
            )
        await self._cache.aset(
            report_key(self._cache, tenant_code, token),
            token_payload(int(record.id), biz),
            ttl=self._limits.error_report_ttl,
        )
        return ImportExecuteResult.model_validate(
            {
                "total": total_rows,
                "success_count": 0,
                "fail_count": 0,
                "blocked_count": 0,
                "committed": False,
                "errors": ConcurrentStableList(),
                "async": True,
                "job_id": int(record.id),
                "report_token": None,
                "duplicate": False,
            }
        )

    async def status(self, *, biz: str, job_id: int, uow: UnitOfWork) -> ImportJobStatus:
        """异步导入状态。

        Args:
            biz: 业务标识。
            job_id: 作业主键。
            uow: 请求级工作单元。

        Returns:
            ImportJobStatus: 状态与汇总。

        Raises:
            ImportBizNotRegisteredError: 作业不属于该业务（`50307`）。
        """
        self._executor.definition(biz)
        async with uow.begin():
            session = cast("DbSession", uow.session)
            repository = ImportJobRepository(session)
            job = await repository.get_job(job_id)
            if job is None or job.job_type != JOB_TYPE:
                raise ImportBizNotRegisteredError(f"导入作业不存在：{job_id}")
            payload = _parse_payload(job.payload)
            if payload.get("biz") != biz:
                raise ImportBizNotRegisteredError(f"作业不属于该导入业务：{job_id}")
            errors_count = await repository.count_errors(job_id)
            errors = await repository.list_errors(job_id, limit=20)
        result = parse_job_result(job.result)
        summary = _summary_from_record(job, result, errors_count)
        token = str(payload.get("report_token") or "") or None
        return ImportJobStatus(
            job_id=int(job.id),
            status=job.status,
            progress_done=int(job.progress_done),
            progress_total=job.progress_total,
            total=summary.total,
            success_count=summary.success_count,
            fail_count=summary.fail_count,
            blocked_count=summary.blocked_count,
            committed=summary.committed,
            errors=build_error_items(errors),
            report_token=token if summary.fail_count > 0 and job.status in JOB_TERMINAL_STATUSES else None,
            message=job.error,
        )

    async def error_report(
        self, *, biz: str, token: str, uow: UnitOfWork, tenant_code: str | None
    ) -> tuple[bytes, str]:
        """生成错误明细 xlsx。

        Args:
            biz: 业务标识。
            token: 错误明细 token。
            uow: 请求级工作单元。
            tenant_code: 租户编码（缓存 key）。

        Returns:
            tuple[bytes, str]: （xlsx 字节, 文件名）。

        Raises:
            ImportReportNotFoundError: token 无效 / 过期 / 无错误（`50306`）。
            ImportReportNotReadyError: 作业未终态（`50308`）。
        """
        definition = self._executor.definition(biz)
        raw = await self._cache.aget(report_key(self._cache, tenant_code, token))
        if not isinstance(raw, Mapping):
            raise ImportReportNotFoundError("错误明细不存在或已过期")
        data = cast("Mapping[str, object]", raw)
        if data.get("biz") != biz:
            raise ImportReportNotFoundError("错误明细不存在或已过期")
        job_id = int(str(data.get("job_id")))
        async with uow.begin():
            session = cast("DbSession", uow.session)
            repository = ImportJobRepository(session)
            job = await repository.get_job(job_id)
            if job is None or job.job_type != JOB_TYPE:
                raise ImportReportNotFoundError("错误明细不存在或已过期")
            if job.status not in JOB_TERMINAL_STATUSES:
                raise ImportReportNotReadyError("作业未完成，错误明细尚未生成")
            errors = await repository.list_all_errors(job_id)
        if not errors:
            raise ImportReportNotFoundError("本次导入没有错误明细")
        titles: ConcurrentStableDict[str, str] = ConcurrentStableDict(
            {column.key: column.title for column in definition.columns}
        )
        report = build_error_report(
            ((int(error.row_no or 0), error.column_key or "", error.message) for error in errors),
            column_titles=titles,
        )
        return report, report_filename(definition.title)


def _runner(factory: Callable[[], JobRunner]) -> JobRunner:
    """调用作业提交器工厂。

    Args:
        factory: 零参工厂。

    Returns:
        JobRunner: 提交器。
    """
    return factory()


def _job_payload(
    biz: str,
    source_key: str,
    file_name: str,
    file_size: int,
    total_rows: int,
    actor: int | None,
    tenant_code: str | None,
    token: str,
) -> ConcurrentStableDict[str, object]:
    """构造作业负载。"""
    return ConcurrentStableDict[str, object](
        {
            "biz": biz,
            "source_key": source_key,
            "file_name": file_name,
            "file_size": file_size,
            "total_rows": total_rows,
            "actor": actor,
            "tenant_code": tenant_code,
            "report_token": token,
        }
    )


def _idem_scope(biz: str, idem_key: str) -> str:
    """幂等键作用域（`biz:clientKey`；超长用 SHA256 截断）。"""
    scope = f"{biz}:{idem_key.strip()}"
    if len(scope) <= 128:
        return scope
    import hashlib

    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


def _tenant_str(tenant_id: int | None) -> str | None:
    """租户主键转字符串。"""
    return None if tenant_id is None else str(tenant_id)


def _summary_of(result: JobResult, total: int, error_rows: int) -> ImportSummary:
    """从作业结果 / 错误行数推导汇总。"""
    output = result.output or ConcurrentStableDict[str, object]()
    success = _int_value(output.get("success_count"), 0)
    fail = _int_value(output.get("fail_count"), error_rows)
    blocked = _int_value(output.get("blocked_count"), max(total - success, 0))
    committed = bool(output.get("committed", result.status == "succeeded"))
    return ImportSummary(
        total=_int_value(output.get("total"), total),
        success_count=success,
        fail_count=fail,
        blocked_count=blocked,
        committed=committed,
    )


def _summary_from_record(job: SysJob, result: ConcurrentStableDict[str, object], error_rows: int) -> ImportSummary:
    """从 `sys_job.result` 推导汇总（未终态返回零值）。"""
    total = _int_value(result.get("total"), 0)
    if job.status not in JOB_TERMINAL_STATUSES:
        return ImportSummary(total=total, success_count=0, fail_count=0, blocked_count=0, committed=False)
    success = _int_value(result.get("success_count"), 0)
    fail = _int_value(result.get("fail_count"), error_rows)
    blocked = _int_value(result.get("blocked_count"), max(total - success, 0))
    committed = bool(result.get("committed", job.status == "succeeded"))
    return ImportSummary(
        total=total,
        success_count=success,
        fail_count=fail,
        blocked_count=blocked,
        committed=committed,
    )


def _int_value(value: object, default: int) -> int:
    """把结果字段转 int（非法回落默认）。"""
    try:
        return int(str(value))
    except TypeError, ValueError:
        return default


def _parse_payload(raw: str | None) -> ConcurrentStableDict[str, object]:
    """解析作业负载 JSON。"""
    if not raw:
        return ConcurrentStableDict[str, object]()
    try:
        value = json.loads(raw)
    except TypeError, ValueError:
        return ConcurrentStableDict[str, object]()
    if not isinstance(value, dict):
        return ConcurrentStableDict[str, object]()
    fields = cast("dict[str, object]", value)
    return ConcurrentStableDict({str(key): item for key, item in fields.items()})


async def _safe_delete(store: ImportSourceStore, key: str) -> None:
    """删除源文件（失败只 warning）。"""
    try:
        await store.delete(key)
    except Exception as exc:  # 清理失败不反噬主流程
        _LOGGER.warning("导入源文件删除失败", key=key, error=str(exc))


async def _safe_release(store: IdempotencyStore, key: str) -> None:
    """释放幂等键（失败只 warning）。"""
    try:
        await store.release(key)
    except Exception as exc:  # 释放失败不覆盖原始异常
        _LOGGER.warning("导入幂等键释放失败", key=key, error=str(exc))
