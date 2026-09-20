"""文件分片上传占位路由：`/api/v1/files`（初始化 / 分片 / 合并 / 取消 / 秒传查询）。

- 统一经分片上传基座（占位实现：内存会话表 + 固定返回）；真实分片托管、秒传判定与上传下载路由随
  文件管理阶段，本路由只做参数校验与委托。
- 初始化入口按需求 02-45 接幂等基座：读 `Idempotency-Key` 头（缺失即跳过），重复初始化复用首次会话。
- 分片状态机、孤儿回收、类型与大小校验、租户配额归文件管理模块（上层），本路由不承载。
"""

import re
from typing import Annotated

from fastapi import Depends, File, Header, Path, Query, UploadFile

from app.api.base import BaseRouter, require_auth
from app.api.deps import get_idempotency_store, get_multipart_upload
from app.core.exceptions import ParamError
from app.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from app.schemas.common import ApiResponse
from app.schemas.storage import (
    DedupResponse,
    MultipartInitiateRequest,
    MultipartPartResponse,
    MultipartSessionResponse,
    StoredObjectResponse,
)
from app.storage.base import BaseMultipartUpload, MultipartInit, MultipartSession

router = BaseRouter(
    key="file",
    prefix="/files",
    tags=["file"],
    dependencies=[Depends(require_auth)],
)

StoreDep = Annotated[BaseMultipartUpload, Depends(get_multipart_upload)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
UploadIdPath = Annotated[str, Path(description="上传会话标识")]
PartNoPath = Annotated[int, Path(ge=1, description="分片序号（从 1 起）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复初始化复用首次会话）"),
]
Sha256Query = Annotated[str, Query(description="整文件 SHA256（64 位小写十六进制）")]
SizeQuery = Annotated[int, Query(gt=0, description="文件字节数（须大于 0）")]
PartDataFile = Annotated[UploadFile, File(description="分片内容（表单字段 data）")]

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _session_response(session: MultipartSession) -> MultipartSessionResponse:
    """把能力域会话映射为路由响应契约（字段一一对应，不隐式透传）。

    Args:
        session: 能力域会话。

    Returns:
        MultipartSessionResponse: 路由响应契约。
    """
    return MultipartSessionResponse(
        upload_id=session.upload_id,
        key=session.key,
        part_size=session.part_size,
        total_parts=session.total_parts,
    )


def _ensure_sha256(sha256: str) -> str:
    """校验 SHA256 格式（64 位小写十六进制）。

    Args:
        sha256: 待校验的 SHA256。

    Returns:
        str: 原值。

    Raises:
        ParamError: 格式非法（10001）。
    """
    if _SHA256_PATTERN.fullmatch(sha256) is None:
        raise ParamError("SHA256 格式非法（应为 64 位小写十六进制）")
    return sha256


@router.post("/uploads")
async def initiate_upload(
    store: StoreDep,
    idempotency: IdempotencyDep,
    req: MultipartInitiateRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """初始化分片上传会话（可按幂等键复用首次会话）。

    Args:
        store: 分片上传基座。
        idempotency: 幂等基座（首次结果复用）。
        req: 初始化请求。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为会话（`MultipartSessionResponse`）。
    """
    init = MultipartInit(
        key=req.key,
        size=req.size,
        sha256=req.sha256,
        mime=req.mime,
        part_size=req.part_size,
    )
    if not idempotency_key:
        return ApiResponse.ok(_session_response(await store.initiate(init)))
    key = build_idempotency_key(key=idempotency_key)
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(MultipartSessionResponse.model_validate(payload))
    session = await store.initiate(init)
    await idempotency.save(key, session.model_dump(mode="json"))
    return ApiResponse.ok(_session_response(session))


@router.put("/uploads/{upload_id}/parts/{part_no}")
async def upload_part(
    store: StoreDep,
    upload_id: UploadIdPath,
    part_no: PartNoPath,
    data: PartDataFile,
) -> ApiResponse:
    """上传单个分片。

    Args:
        store: 分片上传基座。
        upload_id: 上传会话标识。
        part_no: 分片序号。
        data: 分片内容（表单字段 `data`）。

    Returns:
        ApiResponse: 统一响应，data 为分片结果（`MultipartPartResponse`）。
    """
    content = await data.read()
    part = await store.upload_part(upload_id, part_no, content)
    return ApiResponse.ok(MultipartPartResponse(part_no=part.part_no, etag=part.etag, size=part.size))


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(store: StoreDep, upload_id: UploadIdPath) -> ApiResponse:
    """合并分片为最终对象。

    Args:
        store: 分片上传基座。
        upload_id: 上传会话标识。

    Returns:
        ApiResponse: 统一响应，data 为合并产物元数据（`StoredObjectResponse`）。
    """
    stored = await store.complete(upload_id)
    return ApiResponse.ok(
        StoredObjectResponse(
            key=stored.key,
            size=stored.size,
            content_type=stored.content_type,
            etag=stored.etag,
        )
    )


@router.delete("/uploads/{upload_id}")
async def abort_upload(store: StoreDep, upload_id: UploadIdPath) -> ApiResponse:
    """取消上传会话（清理临时分片）。

    Args:
        store: 分片上传基座。
        upload_id: 上传会话标识。

    Returns:
        ApiResponse: 统一响应，data 为 null。
    """
    await store.abort(upload_id)
    return ApiResponse.ok()


@router.get("/dedup")
async def check_dedup(store: StoreDep, sha256: Sha256Query, size: SizeQuery) -> ApiResponse:
    """秒传判定：查询同内容既有对象。

    Args:
        store: 分片上传基座。
        sha256: 整文件 SHA256。
        size: 文件字节数。

    Returns:
        ApiResponse: 统一响应，命中 data 为既有对象引用（`DedupResponse`）、未命中为 null。
    """
    ref = await store.check(_ensure_sha256(sha256), size)
    if ref is None:
        return ApiResponse.ok()
    return ApiResponse.ok(
        DedupResponse(
            key=ref.key,
            size=ref.size,
            content_type=ref.content_type,
            etag=ref.etag,
            stored_at=ref.stored_at,
        )
    )
