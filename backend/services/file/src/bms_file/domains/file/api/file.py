"""文件管理接口：`/api/v1/files`（整包 / 分片 / 断点续传 / 秒传 / 下载预览 / 列表删除 / 内部清理）。

- **权限**：上传挂 `file:upload`、列表挂 `file:query`、取址挂 `file:download`、删除挂 `file:delete`；
  内部清理端点只接受服务 JWT（不经网关）。
- **不代理文件流**：下载 / 预览只回限时预签名地址，客户端直连对象存储。
- **分片上传**：`PUT .../parts/{part_no}` 必带 `X-Part-Sha256`（服务端复算比对）；
  `GET .../multipart/{upload_id}` 回已上传 / 缺失片序号供断点续传。
- **幂等**：初始化入口读 `Idempotency-Key`（缺失即跳过），重复初始化复用首次会话响应。
"""

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, File, Header, Path, Query, UploadFile

from bms_core.api.base import BaseRouter, page_query, require_auth, require_service
from bms_core.api.deps import (
    get_audit_capturer,
    get_config_source,
    get_idempotency_store,
    get_metrics,
    get_multipart_upload,
    get_object_storage,
    get_outbox_store,
    get_service_client,
    get_uow,
)
from bms_core.audit.base import AuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.core.context import current_tenant
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.metrics.base import BaseMetrics
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.servicecall.base import BaseServiceClient
from bms_core.storage.base import BaseMultipartUpload, BaseObjectStorage
from bms_core.tenant_module.quota import TenantQuotaClient
from bms_file.domains.file.schemas.file import (
    DedupRequest,
    DedupResult,
    MultipartCompleteResult,
    MultipartInitiateRequest,
    MultipartInitiateResult,
    MultipartPartResult,
    PresignResult,
    UploadResult,
)
from bms_file.domains.file.services.file import FileService

router = BaseRouter(
    key="file",
    prefix="/files",
    tags=["file"],
    dependencies=[Depends(require_auth)],
)

router_internal = BaseRouter(
    key="file_internal",
    prefix="/files/internal",
    tags=["file-internal"],
)

_REQUIRE_UPLOAD = Depends(require_permission("file:upload"))
_REQUIRE_QUERY = Depends(require_permission("file:query"))
_REQUIRE_DOWNLOAD = Depends(require_permission("file:download"))
_REQUIRE_DELETE = Depends(require_permission("file:delete"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
StorageDep = Annotated[BaseObjectStorage, Depends(get_object_storage)]
MultipartDep = Annotated[BaseMultipartUpload, Depends(get_multipart_upload)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
MetricsDep = Annotated[BaseMetrics, Depends(get_metrics)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]

UploadIdPath = Annotated[str, Path(description="上传会话标识")]
PartNoPath = Annotated[int, Path(ge=1, description="分片序号（从 1 起）")]
FileIdPath = Annotated[int, Path(gt=0, description="文件主键")]
PartShaHeader = Annotated[str, Header(alias="X-Part-Sha256", description="该分片 SHA256（64 位小写十六进制）")]
IdempotencyKeyHeader = Annotated[
    str | None, Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复初始化复用首次会话）")
]
ExpiresQuery = Annotated[int | None, Query(gt=0, le=86400, description="期望有效期（秒；不得超过参数上限）")]
NameQuery = Annotated[str | None, Query(description="文件名关键字（模糊匹配）")]
MimeQuery = Annotated[str | None, Query(description="内容类型前缀（如 image/）")]
UploaderQuery = Annotated[int | None, Query(description="上传人")]
StatusQuery = Annotated[str | None, Query(description="状态（uploading/completed/failed/orphan）")]
FromQuery = Annotated[datetime | None, Query(description="创建时间下限（含）")]
ToQuery = Annotated[datetime | None, Query(description="创建时间上限（含）")]
LimitQuery = Annotated[int | None, Query(gt=0, le=1000, description="单批清理上限")]
OptionalName = Annotated[str | None, Query(description="覆盖文件名（可选，缺省取上传文件名）")]
UploadBody = Annotated[UploadFile, File(description="文件内容（表单字段 file）")]
PartBody = Annotated[UploadFile, File(description="分片内容（表单字段 data）")]


def _service(
    uow: UnitOfWork,
    storage: BaseObjectStorage,
    multipart: BaseMultipartUpload,
    config: BaseConfigSource,
    client: BaseServiceClient,
    outbox: BaseOutboxStore,
    audit: AuditCapturer,
    metrics: BaseMetrics,
) -> FileService:
    """构造文件域服务（请求级依赖组合）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数取数。
        client: 服务间调用客户端（配额记账）。
        outbox: 事务性发件箱。
        audit: 审计捕获器。
        metrics: 指标记录器。

    Returns:
        FileService: 文件域服务。
    """
    quota = TenantQuotaClient(client, tenant_id=current_tenant_id_str(), tenant_code=current_tenant.get())
    return FileService(
        uow=uow,
        storage=storage,
        multipart=multipart,
        config=config,
        quota=quota,
        outbox=outbox,
        audit=audit,
        metrics=metrics,
    )


@router.post("", dependencies=[_REQUIRE_UPLOAD])
async def upload_file(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    file: UploadBody,
    name: OptionalName = None,
) -> ApiResponse:
    """整包上传（≤ `file.upload.max_size`；类型白名单 + 大小 + 配额校验）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        file: 上传文件。
        name: 覆盖文件名（可选）。

    Returns:
        ApiResponse: 统一响应，data 为 `UploadResult`。
    """
    content = await file.read()
    row = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).upload(
        name=name or file.filename or "unnamed",
        data=content,
    )
    return ApiResponse.ok(
        UploadResult(
            file_id=row.id,
            name=row.name,
            mime_type=row.mime_type,
            size=row.size,
            sha256=row.sha256,
            status=row.status,
        )
    )


@router.post("/multipart", dependencies=[_REQUIRE_UPLOAD])
async def initiate_multipart(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    idempotency: IdempotencyDep,
    request: MultipartInitiateRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """分片上传初始化（返回会话标识 / 分片大小 / 分片总数 / 过期时间；可按幂等键复用）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        idempotency: 幂等存储。
        request: 初始化请求。
        idempotency_key: 幂等键（可选）。

    Returns:
        ApiResponse: 统一响应，data 为 `MultipartInitiateResult`。
    """
    service = _service(uow, storage, multipart, config, client, outbox, audit, metrics)
    if idempotency_key:
        token = build_idempotency_key(key=idempotency_key)
        if not await idempotency.begin(token):
            cached = await idempotency.load(token)
            if cached is not None:
                return ApiResponse.ok(MultipartInitiateResult.model_validate(cached))
    row = await service.initiate(name=request.name, size=request.size, sha256=request.sha256, mime=request.mime)
    result = MultipartInitiateResult(
        file_id=row.id,
        upload_id=row.upload_id or "",
        part_size=row.part_size or 0,
        total_parts=row.total_parts or 0,
        expires_at=cast("datetime", row.expires_at),
    )
    if idempotency_key:
        await idempotency.save(build_idempotency_key(key=idempotency_key), result.model_dump(mode="json"))
    return ApiResponse.ok(result)


@router.put("/multipart/{upload_id}/parts/{part_no}", dependencies=[_REQUIRE_UPLOAD])
async def upload_part(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    upload_id: UploadIdPath,
    part_no: PartNoPath,
    part_sha256: PartShaHeader,
    data: PartBody,
) -> ApiResponse:
    """上传单个分片（服务端复算 SHA256 与请求头比对；同片重传为覆盖写）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        upload_id: 会话标识。
        part_no: 分片序号。
        part_sha256: 分片 SHA256（请求头）。
        data: 分片内容。

    Returns:
        ApiResponse: 统一响应，data 为 `MultipartPartResult`。
    """
    part = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).upload_part(
        upload_id=upload_id,
        part_no=part_no,
        data=await data.read(),
        expected_sha256=part_sha256,
    )
    return ApiResponse.ok(MultipartPartResult(part_no=part.part_no, etag=part.etag, size=part.size))


@router.get("/multipart/{upload_id}", dependencies=[_REQUIRE_UPLOAD])
async def multipart_status(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    upload_id: UploadIdPath,
) -> ApiResponse:
    """断点续传状态（已上传 / 缺失分片序号）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        upload_id: 会话标识。

    Returns:
        ApiResponse: 统一响应，data 为 `MultipartStatusResult`。
    """
    result = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).status(upload_id)
    return ApiResponse.ok(result)


@router.post("/multipart/{upload_id}/complete", dependencies=[_REQUIRE_UPLOAD])
async def complete_multipart(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    upload_id: UploadIdPath,
) -> ApiResponse:
    """合并分片为最终对象（幂等：已完成的重复调用回既有结果）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        upload_id: 会话标识。

    Returns:
        ApiResponse: 统一响应，data 为 `MultipartCompleteResult`。
    """
    row = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).complete(upload_id)
    return ApiResponse.ok(
        MultipartCompleteResult(
            file_id=row.id,
            size=row.size,
            sha256=row.sha256,
            status=row.status,
            completed_at=row.completed_at,
        )
    )


@router.delete("/multipart/{upload_id}", dependencies=[_REQUIRE_UPLOAD])
async def abort_multipart(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    upload_id: UploadIdPath,
) -> ApiResponse:
    """取消上传会话（清分片对象与分片行，状态置 failed）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        upload_id: 会话标识。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, storage, multipart, config, client, outbox, audit, metrics).abort(upload_id)
    return ApiResponse.ok()


@router.post("/dedup", dependencies=[_REQUIRE_UPLOAD])
async def dedup(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    request: DedupRequest,
) -> ApiResponse:
    """秒传登记（同租户命中既有对象即建行；未命中 data 为 null）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        request: 秒传请求。

    Returns:
        ApiResponse: 统一响应，data 为 `DedupResult` 或 null。
    """
    row = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).dedup(
        name=request.name,
        size=request.size,
        sha256=request.sha256,
        mime=request.mime,
    )
    if row is None:
        return ApiResponse.ok()
    return ApiResponse.ok(DedupResult(file_id=row.id, dedup=True, size=row.size))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_files(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    page: PageDep,
    name: NameQuery = None,
    mime_type: MimeQuery = None,
    uploader_id: UploaderQuery = None,
    status: StatusQuery = None,
    created_from: FromQuery = None,
    created_to: ToQuery = None,
) -> ApiResponse:
    """文件列表（名称 / 类型 / 上传人 / 状态 / 时间范围筛选 + 分页）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        page: 分页参数。
        name: 名称关键字。
        mime_type: 内容类型前缀。
        uploader_id: 上传人。
        status: 状态。
        created_from: 创建时间下限。
        created_to: 创建时间上限。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    result = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).page(
        page=page.page,
        size=page.size,
        name=name,
        mime_type=mime_type,
        uploader_id=uploader_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
    )
    return ApiResponse.ok(result)


@router.get("/{file_id}/download-url", dependencies=[_REQUIRE_DOWNLOAD])
async def download_url(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    file_id: FileIdPath,
    expires_in: ExpiresQuery = None,
) -> ApiResponse:
    """取限时预签名下载地址（后端不代理文件流；过期即不可下载）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        file_id: 文件主键。
        expires_in: 期望有效期（秒）。

    Returns:
        ApiResponse: 统一响应，data 为 `PresignResult`。
    """
    result = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).presign(
        file_id=file_id, preview=False, expires_in=expires_in
    )
    return ApiResponse.ok(
        PresignResult(file_id=file_id, url=result.url, expires_in=result.expires_in, method=result.method)
    )


@router.get("/{file_id}/preview-url", dependencies=[_REQUIRE_DOWNLOAD])
async def preview_url(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    file_id: FileIdPath,
    expires_in: ExpiresQuery = None,
) -> ApiResponse:
    """取限时预签名预览地址（仅图片 / PDF 直开）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        file_id: 文件主键。
        expires_in: 期望有效期（秒）。

    Returns:
        ApiResponse: 统一响应，data 为 `PresignResult`。
    """
    result = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).presign(
        file_id=file_id, preview=True, expires_in=expires_in
    )
    return ApiResponse.ok(
        PresignResult(file_id=file_id, url=result.url, expires_in=result.expires_in, method=result.method)
    )


@router.delete("/{file_id}", dependencies=[_REQUIRE_DELETE])
async def delete_file(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    file_id: FileIdPath,
) -> ApiResponse:
    """删除文件（软删元数据；对象保留、配额不释放，物理清理归 13_01）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        file_id: 文件主键。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, storage, multipart, config, client, outbox, audit, metrics).delete(file_id)
    return ApiResponse.ok()


@router_internal.post("/cleanup-orphans", dependencies=[Depends(require_service())])
async def cleanup_orphans(
    uow: UowDep,
    storage: StorageDep,
    multipart: MultipartDep,
    config: ConfigDep,
    client: ClientDep,
    outbox: OutboxDep,
    audit: AuditDep,
    metrics: MetricsDep,
    limit: LimitQuery = None,
) -> ApiResponse:
    """孤儿回收（服务间内部端点；由内置任务 `cleanup_orphan_parts` 触发）。

    Args:
        uow: 工作单元。
        storage: 对象存储。
        multipart: 分片上传。
        config: 系统参数。
        client: 服务调用客户端。
        outbox: 发件箱。
        audit: 审计捕获器。
        metrics: 指标。
        limit: 单批上限。

    Returns:
        ApiResponse: 统一响应，data 为 `CleanupResult`。
    """
    result = await _service(uow, storage, multipart, config, client, outbox, audit, metrics).cleanup_orphans(
        limit=limit
    )
    return ApiResponse.ok(result)
