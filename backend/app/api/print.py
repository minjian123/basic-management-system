"""打印与导出 PDF 占位路由：`/api/v1/prints`（单条导出 PDF / 批量打印 / 模板清单 / 模板详情）。

- 四端点统一经打印能力域出口（模板来源与导出两契约；占位实现固定返回），**均需登录**（打印 / 导出属业务
  操作），权限码由上层声明、基座不内建。
- 两写接口（单条导出 / 批量打印）按需接幂等基座（02-25）：读 `Idempotency-Key` 头（缺失即跳过），
  作用域绑当前租户位（产物与批量结果不宜跨租户复用），重复请求复用首次结果。
- `GET /prints/templates/{template_key}` 未命中由打印子段错误统一转 404 / `50201`。
- 真实 PDF 渲染 / 模板定义来源 / 产物落存储与限时取址随通用能力、表单定制与文件管理阶段，
  本路由只做参数校验与委托。
"""

from typing import Annotated

from fastapi import Depends, Header, Path, Query

from app.api.base import BaseRouter, require_auth
from app.api.deps import (
    get_idempotency_store,
    get_print_exporter,
    get_print_template_provider,
    get_tenant,
)
from app.api.tenant import current_code_of
from app.db.tenant import TenantContext
from app.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from app.print.base import (
    BasePrintExporter,
    BasePrintTemplateProvider,
    PrintBatchResult,
    PrintDocument,
    PrintExportResult,
    PrintOptions,
    PrintTemplateInfo,
)
from app.schemas.common import ApiResponse
from app.schemas.print import (
    PrintBatchRequest,
    PrintBatchResponse,
    PrintDocumentPayload,
    PrintExportRequest,
    PrintExportResponse,
    PrintOptionsPayload,
    PrintTemplateInfoResponse,
    PrintTemplateListResponse,
    PrintVariableResponse,
)

router = BaseRouter(
    key="print",
    prefix="/prints",
    tags=["print"],
    dependencies=[Depends(require_auth)],
)

ExporterDep = Annotated[BasePrintExporter, Depends(get_print_exporter)]
TemplateDep = Annotated[BasePrintTemplateProvider, Depends(get_print_template_provider)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
TemplateKeyPath = Annotated[str, Path(description="打印模板键")]
BizTypeQuery = Annotated[str | None, Query(description="单据类型（缺省全部）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复导出 / 批量复用首次结果）"),
]


def _to_document(payload: PrintDocumentPayload) -> PrintDocument:
    """把路由单据数据映射为能力域契约。

    Args:
        payload: 路由单据数据。

    Returns:
        PrintDocument: 能力域单据数据。
    """
    return PrintDocument(biz_key=payload.biz_key, fields=payload.fields, rows=payload.rows)


def _to_options(payload: PrintOptionsPayload | None) -> PrintOptions | None:
    """把路由渲染选项映射为能力域契约（缺省保留 None，由实现侧取平台缺省）。

    Args:
        payload: 路由渲染选项（可为 None）。

    Returns:
        PrintOptions | None: 能力域渲染选项；未提供为 None。
    """
    if payload is None:
        return None
    return PrintOptions(
        paper=payload.paper,
        orientation=payload.orientation,
        tone=payload.tone,
        watermark=payload.watermark,
        printed_by=payload.printed_by,
    )


def _export_response(result: PrintExportResult) -> PrintExportResponse:
    """把能力域导出产物映射为路由响应契约（字段一一对应）。

    Args:
        result: 能力域导出产物。

    Returns:
        PrintExportResponse: 路由响应契约。
    """
    return PrintExportResponse(
        object_key=result.object_key,
        file_id=result.file_id,
        file_name=result.file_name,
        size=result.size,
        content_type=result.content_type,
        url=result.url,
        expires_in=result.expires_in,
        message=result.message,
    )


def _batch_response(result: PrintBatchResult) -> PrintBatchResponse:
    """把能力域批量结果映射为路由响应契约（字段一一对应）。

    Args:
        result: 能力域批量结果。

    Returns:
        PrintBatchResponse: 路由响应契约。
    """
    return PrintBatchResponse(
        task_id=result.task_id,
        total=result.total,
        succeeded=result.succeeded,
        failed=result.failed,
        items=[_export_response(item) for item in result.items],
        message=result.message,
    )


def _template_response(info: PrintTemplateInfo) -> PrintTemplateInfoResponse:
    """把能力域模板定义映射为路由响应契约（字段一一对应）。

    Args:
        info: 能力域模板定义。

    Returns:
        PrintTemplateInfoResponse: 路由响应契约。
    """
    return PrintTemplateInfoResponse(
        key=info.key,
        name=info.name,
        biz_type=info.biz_type,
        variables=[PrintVariableResponse(key=item.key, label=item.label) for item in info.variables],
        status=info.status,
    )


@router.post("/exports")
async def export_pdf(
    exporter: ExporterDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    req: PrintExportRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """导出单条单据 PDF（可按幂等键复用首次结果）。

    Args:
        exporter: 打印导出基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        req: 导出请求（模板键 / 单据数据 / 渲染选项）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为导出产物（`PrintExportResponse`）。
    """
    document = _to_document(req.document)
    options = _to_options(req.options)
    if not idempotency_key:
        return ApiResponse.ok(_export_response(await exporter.export_pdf(req.template_key, document, options=options)))
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(PrintExportResponse.model_validate(payload))
    result = await exporter.export_pdf(req.template_key, document, options=options)
    await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(_export_response(result))


@router.post("/batch")
async def batch_print(
    exporter: ExporterDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    req: PrintBatchRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """批量打印多单据（可按幂等键复用首次结果）。

    Args:
        exporter: 打印导出基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        req: 批量请求（模板键 / 单据键集合 / 批量模式 / 渲染选项）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为批量结果（`PrintBatchResponse`）。
    """
    options = _to_options(req.options)
    if not idempotency_key:
        return ApiResponse.ok(
            _batch_response(
                await exporter.batch_print(req.keys, template_key=req.template_key, mode=req.mode, options=options)
            )
        )
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(PrintBatchResponse.model_validate(payload))
    result = await exporter.batch_print(req.keys, template_key=req.template_key, mode=req.mode, options=options)
    await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(_batch_response(result))


@router.get("/templates")
async def list_templates(provider: TemplateDep, biz_type: BizTypeQuery = None) -> ApiResponse:
    """取打印模板清单（可按单据类型过滤）。

    Args:
        provider: 打印模板来源基座。
        biz_type: 单据类型查询参数（可选）。

    Returns:
        ApiResponse: 统一响应，data 为模板清单（`PrintTemplateListResponse`）。
    """
    templates = await provider.list(biz_type=biz_type)
    return ApiResponse.ok(PrintTemplateListResponse(templates=[_template_response(item) for item in templates]))


@router.get("/templates/{template_key}")
async def get_template(provider: TemplateDep, template_key: TemplateKeyPath) -> ApiResponse:
    """取单模板定义（变量清单）。

    Args:
        provider: 打印模板来源基座。
        template_key: 打印模板键。

    Returns:
        ApiResponse: 统一响应，data 为模板定义（`PrintTemplateInfoResponse`）。
    """
    return ApiResponse.ok(_template_response(await provider.get(template_key)))
