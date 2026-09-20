"""文件分片上传占位路由的请求 / 响应契约（与 `app/storage/` 能力域契约字段一一对应）。

- `MultipartInitiateRequest`：初始化请求（对应能力域 `MultipartInit`）。
- `MultipartSessionResponse` / `MultipartPartResponse` / `StoredObjectResponse`：会话 / 分片 / 合并产物响应。
- `DedupResponse`：秒传命中响应（对应能力域 `ExistingObjectRef`；未命中时统一响应 `data` 为 `null`）。

口径：路由契约与能力域契约**字段名一致**，由路由层显式映射（不隐式透传字典），保证 OpenAPI 契约稳定；
分片内容经表单体（`multipart/form-data`）承载，不入本模块。
"""

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema

__all__ = [
    "DedupResponse",
    "MultipartInitiateRequest",
    "MultipartPartResponse",
    "MultipartSessionResponse",
    "StoredObjectResponse",
]


class MultipartInitiateRequest(BaseSchema):
    """分片上传初始化请求。"""

    key: str = Field(min_length=1, description="目标对象 key（上层按 bms:{租户}:files:{业务键} 构造）")
    size: int = Field(gt=0, description="文件字节数（须大于 0；空文件不走分片上传）")
    sha256: str = Field(min_length=1, description="整文件 SHA256（供秒传判定与合并校验）")
    mime: str | None = Field(default=None, description="内容类型（可空）")
    part_size: int | None = Field(default=None, gt=0, description="分片大小（字节）；缺省取基座缺省分片大小")


class MultipartSessionResponse(BaseSchema):
    """分片上传会话响应。"""

    upload_id: str = Field(description="会话标识")
    key: str = Field(description="目标对象 key（回显）")
    part_size: int = Field(description="分片大小（字节）")
    total_parts: int = Field(description="分片总数（part_no 取值 1 ~ total_parts）")


class MultipartPartResponse(BaseSchema):
    """分片上传响应。"""

    part_no: int = Field(ge=1, description="分片序号（从 1 起）")
    etag: str = Field(description="分片 etag")
    size: int = Field(ge=0, description="分片字节数")


class StoredObjectResponse(BaseSchema):
    """合并产物响应（分片合并后的对象元数据）。"""

    key: str = Field(description="对象 key")
    size: int = Field(ge=0, description="对象字节数")
    content_type: str | None = Field(default=None, description="内容类型")
    etag: str | None = Field(default=None, description="对象 etag")


class DedupResponse(BaseSchema):
    """秒传命中响应（既有对象引用；未命中时统一响应 `data` 为 `null`）。"""

    key: str = Field(description="既有对象 key")
    size: int = Field(ge=0, description="对象字节数")
    content_type: str | None = Field(default=None, description="内容类型")
    etag: str | None = Field(default=None, description="对象 etag")
    stored_at: datetime | None = Field(default=None, description="对象写入时间")
