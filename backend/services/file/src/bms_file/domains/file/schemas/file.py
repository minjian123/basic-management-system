"""文件域接口契约：上传 / 分片 / 秒传 / 列表 / 取址 / 清理。

口径：请求与响应一律继承 `BaseSchema`；列表复用 `BasePageResponse`；时间字段为 UTC。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, BaseSchema
from bms_core.schemas.pagination import BasePageResponse

__all__ = [
    "CleanupResult",
    "DedupRequest",
    "DedupResult",
    "FileItem",
    "FilePage",
    "MultipartCompleteResult",
    "MultipartInitiateRequest",
    "MultipartInitiateResult",
    "MultipartPartResult",
    "MultipartStatusResult",
    "PresignResult",
    "UploadResult",
]


class FileItem(BaseSchema):
    """文件元数据（列表 / 详情同构）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="文件主键")
    name: str = Field(description="原始文件名")
    ext: str | None = Field(default=None, description="扩展名（小写，无点）")
    mime_type: str = Field(description="服务端嗅探的内容类型")
    size: int = Field(description="字节数")
    sha256: str = Field(description="整文件 SHA256")
    source: str = Field(description="来源（upload/dedup/print/export）")
    status: str = Field(description="状态（uploading/completed/failed/orphan）")
    uploader_id: int | None = Field(default=None, description="上传人")
    total_parts: int | None = Field(default=None, description="分片总数（整包为空）")
    uploaded_parts: int | None = Field(default=None, description="已上传片数")
    expires_at: datetime | None = Field(default=None, description="会话过期时刻（UTC）")
    completed_at: datetime | None = Field(default=None, description="完成时刻（UTC）")
    created_at: datetime = Field(description="创建时间（UTC）")
    version: int = Field(description="乐观锁版本")


class FilePage(BasePageResponse[FileItem]):
    """文件列表分页响应。"""


class UploadResult(BaseSchema):
    """整包上传结果。"""

    file_id: int = Field(description="文件主键")
    name: str = Field(description="原始文件名")
    mime_type: str = Field(description="服务端嗅探的内容类型")
    size: int = Field(description="字节数")
    sha256: str = Field(description="整文件 SHA256")
    status: str = Field(description="状态（整包上传恒为 completed）")


class MultipartInitiateRequest(BaseSchema):
    """分片初始化请求。"""

    name: str = Field(min_length=1, max_length=255, description="原始文件名（含扩展名）")
    size: int = Field(gt=0, description="文件字节数（须大于 0）")
    sha256: str = Field(min_length=64, max_length=64, description="整文件 SHA256（64 位小写十六进制）")
    mime: str | None = Field(default=None, max_length=128, description="声明的内容类型（仅供预检，不作真值）")


class MultipartInitiateResult(BaseSchema):
    """分片初始化结果。"""

    file_id: int = Field(description="文件主键")
    upload_id: str = Field(description="会话标识（后续分片 / 合并 / 取消均以它为准）")
    part_size: int = Field(description="分片大小（字节）")
    total_parts: int = Field(description="分片总数（part_no 取值 1 ~ total_parts）")
    expires_at: datetime = Field(description="会话过期时刻（UTC）")


class MultipartPartResult(BaseSchema):
    """分片上传结果。"""

    part_no: int = Field(ge=1, description="分片序号")
    etag: str = Field(description="分片 etag")
    size: int = Field(ge=0, description="分片字节数")


class MultipartStatusResult(BaseSchema):
    """断点续传状态。"""

    file_id: int = Field(description="文件主键")
    upload_id: str = Field(description="会话标识")
    status: str = Field(description="文件状态")
    part_size: int = Field(description="分片大小（字节）")
    total_parts: int = Field(description="分片总数")
    uploaded_parts: int = Field(description="已上传片数")
    uploaded: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(description="已上传分片序号")
    missing: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        description="缺失分片序号（重传只补这些）"
    )
    expires_at: datetime | None = Field(default=None, description="会话过期时刻（UTC）")


class MultipartCompleteResult(BaseSchema):
    """合并完成结果。"""

    file_id: int = Field(description="文件主键")
    size: int = Field(description="字节数")
    sha256: str = Field(description="整文件 SHA256")
    status: str = Field(description="状态（completed）")
    completed_at: datetime | None = Field(default=None, description="完成时刻（UTC）")


class DedupRequest(BaseSchema):
    """秒传登记请求。"""

    name: str = Field(min_length=1, max_length=255, description="原始文件名（含扩展名）")
    size: int = Field(gt=0, description="文件字节数")
    sha256: str = Field(min_length=64, max_length=64, description="整文件 SHA256")
    mime: str | None = Field(default=None, max_length=128, description="声明的内容类型（仅供预检）")


class DedupResult(BaseSchema):
    """秒传命中结果（未命中时统一响应 data 为 null）。"""

    file_id: int = Field(description="新建的文件主键（复用既有对象）")
    dedup: bool = Field(default=True, description="固定 true（命中秒传）")
    size: int = Field(description="字节数")


class PresignResult(BaseSchema):
    """预签名取址结果（后端不代理文件流）。"""

    file_id: int = Field(description="文件主键")
    url: str = Field(description="限时预签名地址")
    expires_in: int = Field(description="有效期（秒）")
    method: str = Field(description="HTTP 方法")


class CleanupResult(BaseSchema):
    """孤儿回收结果（内部端点 / 内置任务摘要）。"""

    scanned: int = Field(description="扫描到的超期上传中记录数")
    orphaned: int = Field(description="已置为 orphan 的记录数")
    failed: int = Field(description="清理失败的记录数")
