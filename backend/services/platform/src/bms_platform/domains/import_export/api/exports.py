"""导出接口：列表 Excel / 列表 PDF / 异步作业状态（`/api/v1/exports`）。

- 三端点均需登录 + `export:download`；用户维度限流（`export.rate_limit.*`）。
- Excel：同步回文件流（`Content-Disposition` RFC 5987 中文名）；超阈值回异步受理；0 行回空结果。
- PDF：同步回产物限时取址；超阈值回异步受理。
- 状态：作业终态 + 每次重新预签名的产物取址（产物过期时 artifact 为空）。
- 留痕：每次导出落 `AuditCapturer.capture`（`table=sys_export`，`model_id` 异步为作业主键、同步为 0）；
  明文导出额外写 `warning` 结构化日志。
"""

from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, Path, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_audit_capturer,
    get_config_source,
    get_exporter,
    get_masker,
    get_object_storage,
    get_print_exporter,
    get_rate_limiter,
    get_uow,
)
from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_tenant, current_user_id
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.runner import JobRunner
from bms_core.masking.base import BaseMasker
from bms_core.permission.base import require_permission
from bms_core.print.base import DEFAULT_PAPER, PRINT_ORIENTATIONS, BasePrintExporter
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.schemas.common import ApiResponse
from bms_core.storage.base import BaseObjectStorage
from bms_core.transfer.artifacts import ObjectStorageExportArtifactStore
from bms_core.transfer.export_definition import ExportDefinitionRegistry, parse_ids
from bms_core.transfer.export_limits import ExportLimits
from bms_core.transfer.exporter import BaseExporter
from bms_core.transfer.openpyxl_io import XLSX_CONTENT_TYPE
from bms_platform.domains.import_export.schemas.exports import (
    ExportArtifact,
    ExportAsyncAccepted,
    ExportEmptyResult,
    ExportJobStatus,
    ExportListPdfResult,
)
from bms_platform.domains.import_export.services.exports import (
    EXPORT_STATUS_URL,
    KIND_EXCEL,
    KIND_PDF,
    ExportArtifactData,
    ExportExecutor,
    ExportOutcome,
    ExportPayload,
    ExportService,
    as_int,
    validate_print_options,
)

__all__ = ["build_export_router"]

_LOGGER = get_logger("bms")

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
StorageDep = Annotated[BaseObjectStorage, Depends(get_object_storage)]
ExporterDep = Annotated[BaseExporter, Depends(get_exporter)]
PrintExporterDep = Annotated[BasePrintExporter, Depends(get_print_exporter)]
MaskerDep = Annotated[BaseMasker, Depends(get_masker)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]

BizPath = Annotated[str, Path(min_length=1, max_length=64, description="业务标识（users / roles）")]
KeywordQuery = Annotated[str | None, Query(max_length=128, description="关键字（与列表接口同名同义）")]
StatusQuery = Annotated[str | None, Query(max_length=16, description="状态筛选（enabled / disabled）")]
IdsQuery = Annotated[str | None, Query(description="选中行导出（逗号分隔雪花 ID；空 = 按筛选全量）")]
OrderByQuery = Annotated[str | None, Query(max_length=64, description="排序字段（各定义白名单）")]
OrderQuery = Annotated[str, Query(description="排序方向（asc / desc）")]
PaperQuery = Annotated[str, Query(description="纸张（A4 / A5 / custom）")]
OrientationQuery = Annotated[str, Query(description="纸张方向（portrait / landscape）")]
WatermarkQuery = Annotated[str, Query(max_length=64, description="水印文案")]
TitleQuery = Annotated[str, Query(max_length=64, description="PDF 标题（缺省取定义标题）")]

_REQUIRE_EXPORT = Depends(require_permission("export:download"))

_AUDIT_TABLE = "sys_export"
"""审计逻辑表名（导出动作留痕；落库归 06_01）。"""

_AUDIT_SYNC = 0
"""同步导出无作业记录时的审计 model_id 占位。"""

_EMPTY_MESSAGE = "当前筛选无数据可导出"
"""0 行提示文案。"""

_ASYNC_MESSAGE = "数据量较大，已转后台导出"
"""异步受理提示文案。"""


class _ExportDeps(BaseFrameworkObject):
    """一次请求的导出依赖集合。"""

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        config: BaseConfigSource,
        storage: BaseObjectStorage,
        exporter: BaseExporter,
        print_exporter: BasePrintExporter,
        audit: AuditCapturer,
        limiter: BaseRateLimiter,
        definitions_factory: Callable[[], ExportDefinitionRegistry],
        runner_factory: Callable[[], JobRunner],
    ) -> None:
        self.uow = uow
        self.config = config
        self.storage = storage
        self.exporter = exporter
        self.print_exporter = print_exporter
        self.audit = audit
        self.limiter = limiter
        self.definitions_factory = definitions_factory
        self.runner_factory = runner_factory


def build_export_router(
    *,
    definitions_factory: Callable[[], ExportDefinitionRegistry],
    runner_factory: Callable[[], JobRunner],
) -> BaseRouter:
    """构造导出业务路由。

    Args:
        definitions_factory: 导出定义装配函数（服务根注入）。
        runner_factory: 作业提交器工厂（服务根注入）。

    Returns:
        BaseRouter: `/exports` 路由。
    """
    router = BaseRouter(
        key="import_export_exports",
        prefix="/exports",
        tags=["export"],
        dependencies=[Depends(require_auth)],
    )

    def deps_of(
        uow: UowDep,
        config: ConfigDep,
        storage: StorageDep,
        exporter: ExporterDep,
        print_exporter: PrintExporterDep,
        audit: AuditDep,
        limiter: LimiterDep,
    ) -> _ExportDeps:
        """收集请求依赖。

        Args:
            uow: 请求级工作单元。
            config: 系统参数取数。
            storage: 对象存储。
            exporter: Excel 导出器。
            print_exporter: 打印导出。
            audit: 审计捕获。
            limiter: 限流器。

        Returns:
            _ExportDeps: 依赖集合。
        """
        return _ExportDeps(
            uow=uow,
            config=config,
            storage=storage,
            exporter=exporter,
            print_exporter=print_exporter,
            audit=audit,
            limiter=limiter,
            definitions_factory=definitions_factory,
            runner_factory=runner_factory,
        )

    async def _service(deps: _ExportDeps) -> ExportService:
        """按请求参数构造导出服务（定义注册表 + 出口 + 参数）。

        Args:
            deps: 请求依赖。

        Returns:
            ExportService: 导出服务。
        """
        limits = await ExportLimits.load(deps.config)
        executor = ExportExecutor(
            definitions=deps.definitions_factory(),
            excel_exporter=deps.exporter,
            print_exporter=deps.print_exporter,
            artifacts=ObjectStorageExportArtifactStore(deps.storage),
            limits=limits,
        )
        return ExportService(executor=executor, runner_factory=deps.runner_factory, limits=limits)

    async def _rate_limit(deps: _ExportDeps) -> None:
        """用户维度限流（`export.rate_limit.*`）。

        Args:
            deps: 请求依赖。
        """
        user_id = current_user_id.get()
        if user_id is None:  # pragma: no cover - 鉴权路由下不可达；防御性分支
            return
        limits = await ExportLimits.load(deps.config)
        key = build_rate_limit_key(dimension="user", target=str(user_id), tenant=current_tenant.get())
        await deps.limiter.require(key, RateLimitRule(limit=limits.rate_limit, window=limits.rate_limit_window))

    def _payload(
        *,
        biz: str,
        kind: str,
        masker: BaseMasker,
        keyword: str | None,
        status: str | None,
        ids: str | None,
        order_by: str | None,
        order: str,
        title: str = "",
        paper: str = "",
        orientation: str = "",
        watermark: str = "",
    ) -> ExportPayload:
        """把查询参数解析为导出意图（`ids` 非法即拒）。

        Args:
            biz: 业务标识。
            kind: 导出类型。
            masker: 请求期掩码器（判定明文权限）。
            keyword: 关键字。
            status: 状态筛选。
            ids: 选中集合（逗号分隔）。
            order_by: 排序字段。
            order: 排序方向。
            title: PDF 标题。
            paper: 纸张。
            orientation: 纸张方向。
            watermark: 水印。

        Returns:
            ExportPayload: 导出意图。
        """
        parsed_ids = parse_ids(ids)
        tenant = current_tenant_context()
        params: ConcurrentStableDict[str, str] = ConcurrentStableDict()
        if keyword:
            params.set("kw", keyword)
        if status:
            params.set("status", status)
        if order_by:
            params.set("order_by", order_by)
        params.set("order", order)
        paper_value = paper or DEFAULT_PAPER
        orientation_value = orientation or PRINT_ORIENTATIONS[0]
        # 参数校验前置：非法纸张 / 方向在取数之前就失败（空结果不得吞掉参数错误）
        validate_print_options(paper=paper_value, orientation=orientation_value)
        return ExportPayload(
            biz=biz,
            kind=kind,
            params=params,
            ids=ConcurrentStableList(str(value) for value in parsed_ids),
            plain=masker.check_plain(),
            actor=current_user_id.get(),
            tenant_code=tenant.code,
            title=title,
            paper=paper_value,
            orientation=orientation_value,
            watermark=watermark,
        )

    def _audit(
        deps: _ExportDeps,
        payload: ExportPayload,
        *,
        total: int,
        job_id: int | None,
        file_name: str | None,
    ) -> None:
        """记录导出动作（审计 capture + 明文 warning）。

        Args:
            deps: 请求依赖。
            payload: 导出意图。
            total: 导出条数。
            job_id: 作业主键（同步为 None）。
            file_name: 文件名（异步为 None）。
        """
        deps.audit.capture(
            table=_AUDIT_TABLE,
            model_id=job_id if job_id is not None else _AUDIT_SYNC,
            changes=ConcurrentStableList(
                (
                    FieldChange(field="biz", new=payload.biz),
                    FieldChange(field="kind", new=payload.kind),
                    FieldChange(field="rows", new=total),
                    FieldChange(field="plain", new=payload.plain),
                    FieldChange(field="file_name", new=file_name),
                )
            ),
            actor=payload.actor,
        )
        if payload.plain:
            _LOGGER.warning(
                "明文导出",
                biz=payload.biz,
                kind=payload.kind,
                rows=total,
                actor=payload.actor,
                file_name=file_name,
            )

    def _json(data: object) -> JSONResponse:
        """统一响应信封的 JSON 响应（文件流端点内的非文件分支）。

        Args:
            data: 响应数据模型。

        Returns:
            JSONResponse: JSON 响应。
        """
        return JSONResponse(content=jsonable_encoder(ApiResponse.ok(data)))

    def _async_accepted(outcome: ExportOutcome) -> ExportAsyncAccepted:
        """构造异步受理响应。

        Args:
            outcome: 编排结果。

        Returns:
            ExportAsyncAccepted: 异步受理。
        """
        return ExportAsyncAccepted(
            job_id=outcome.job_id or 0,
            total=outcome.total,
            status_url=EXPORT_STATUS_URL.format(job_id=outcome.job_id or 0),
            message=_ASYNC_MESSAGE,
        )

    def _artifact(artifact: ExportArtifactData) -> ExportArtifact:
        """服务层产物 → 响应契约。

        Args:
            artifact: 服务层产物。

        Returns:
            ExportArtifact: 响应契约。
        """
        return ExportArtifact(
            object_key=artifact.object_key,
            file_name=artifact.file_name,
            size=artifact.size,
            content_type=artifact.content_type,
            url=artifact.url,
            expires_in=artifact.expires_in,
        )

    def _disposition(filename: str) -> str:
        """RFC 5987 下载文件名（中文安全）。

        Args:
            filename: 文件名。

        Returns:
            str: `Content-Disposition` 头值。
        """
        return f"attachment; filename*=UTF-8''{quote(filename)}"

    @router.get("/jobs/{job_id}", dependencies=[_REQUIRE_EXPORT])
    async def get_export_job(
        job_id: Annotated[int, Path(gt=0, description="导出作业主键")],
        deps: Annotated[_ExportDeps, Depends(deps_of)],
    ) -> ApiResponse[ExportJobStatus]:
        """异步导出状态 / 进度 / 产物限时取址。

        Args:
            job_id: 作业主键。
            deps: 请求依赖。

        Returns:
            ApiResponse: 状态。
        """
        await _rate_limit(deps)
        status = await (await _service(deps)).status(job_id=job_id, uow=deps.uow)
        artifact = status.get("artifact")
        return ApiResponse.ok(
            ExportJobStatus(
                job_id=as_int(status.get("job_id"), job_id),
                status=str(status.get("status") or ""),
                kind=str(status.get("kind") or ""),
                biz=str(status.get("biz") or ""),
                total=as_int(status.get("total")),
                done=as_int(status.get("done")),
                artifact=_artifact(artifact) if isinstance(artifact, ExportArtifactData) else None,
                message=None if status.get("message") is None else str(status.get("message")),
            )
        )

    @router.get("/{biz}", dependencies=[_REQUIRE_EXPORT])
    async def export_excel(
        biz: BizPath,
        deps: Annotated[_ExportDeps, Depends(deps_of)],
        masker: MaskerDep,
        kw: KeywordQuery = None,
        status: StatusQuery = None,
        ids: IdsQuery = None,
        order_by: OrderByQuery = None,
        order: OrderQuery = "asc",
    ) -> Response:
        """按当前筛选导出 Excel（同步文件流 / 异步受理 / 空结果）。

        Args:
            biz: 业务标识。
            deps: 请求依赖。
            masker: 请求期掩码器（明文判定）。
            kw: 关键字。
            status: 状态筛选。
            ids: 选中集合。
            order_by: 排序字段。
            order: 排序方向。

        Returns:
            Response: xlsx 文件流或 JSON（异步 / 空）。
        """
        await _rate_limit(deps)
        payload = _payload(
            biz=biz,
            kind=KIND_EXCEL,
            masker=masker,
            keyword=kw,
            status=status,
            ids=ids,
            order_by=order_by,
            order=order,
        )
        tenant = current_tenant_context()
        outcome = await (await _service(deps)).export_excel(
            payload=payload,
            uow=deps.uow,
            masker=masker,
            tenant_id=tenant.tenant_id,
        )
        if outcome.empty:
            _audit(deps, payload, total=0, job_id=None, file_name=None)
            return _json(ExportEmptyResult(message=_EMPTY_MESSAGE))
        if outcome.async_mode:
            _audit(deps, payload, total=outcome.total, job_id=outcome.job_id, file_name=None)
            return _json(_async_accepted(outcome))
        _audit(deps, payload, total=outcome.total, job_id=None, file_name=outcome.file_name)
        return Response(
            content=outcome.content or b"",
            media_type=XLSX_CONTENT_TYPE,
            headers={"Content-Disposition": _disposition(outcome.file_name or "export.xlsx")},
        )

    @router.get("/{biz}/pdf", dependencies=[_REQUIRE_EXPORT])
    async def export_list_pdf(
        biz: BizPath,
        deps: Annotated[_ExportDeps, Depends(deps_of)],
        masker: MaskerDep,
        kw: KeywordQuery = None,
        status: StatusQuery = None,
        ids: IdsQuery = None,
        order_by: OrderByQuery = None,
        order: OrderQuery = "asc",
        paper: PaperQuery = "A4",
        orientation: OrientationQuery = "portrait",
        watermark: WatermarkQuery = "",
        title: TitleQuery = "",
    ) -> Response:
        """按当前筛选导出列表 PDF（同步产物取址 / 异步受理 / 空结果）。

        Args:
            biz: 业务标识。
            deps: 请求依赖。
            masker: 请求期掩码器。
            kw: 关键字。
            status: 状态筛选。
            ids: 选中集合。
            order_by: 排序字段。
            order: 排序方向。
            paper: 纸张。
            orientation: 纸张方向。
            watermark: 水印。
            title: 标题。

        Returns:
            Response: JSON（同步产物 / 异步 / 空）。
        """
        await _rate_limit(deps)
        payload = _payload(
            biz=biz,
            kind=KIND_PDF,
            masker=masker,
            keyword=kw,
            status=status,
            ids=ids,
            order_by=order_by,
            order=order,
            title=title,
            paper=paper,
            orientation=orientation,
            watermark=watermark,
        )
        tenant = current_tenant_context()
        outcome = await (await _service(deps)).export_pdf(
            payload=payload,
            uow=deps.uow,
            masker=masker,
            tenant_id=tenant.tenant_id,
        )
        if outcome.empty:
            _audit(deps, payload, total=0, job_id=None, file_name=None)
            return _json(ExportEmptyResult(message=_EMPTY_MESSAGE))
        if outcome.async_mode:
            _audit(deps, payload, total=outcome.total, job_id=outcome.job_id, file_name=None)
            return _json(_async_accepted(outcome))
        artifact = outcome.artifact
        _audit(
            deps,
            payload,
            total=outcome.total,
            job_id=None,
            file_name=artifact.file_name if artifact is not None else None,
        )
        return _json(
            ExportListPdfResult(
                total=outcome.total,
                artifact=_artifact(artifact) if artifact is not None else None,
            )
        )

    return router
