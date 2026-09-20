"""文件存储能力域：对象存储与分片上传两契约（真实实现随文件管理阶段回补）。

- `STORAGE_BUCKET`：默认私有桶名（`bms-files`）；`DEFAULT_PRESIGN_TTL`：预签名默认有效期（秒，1 小时）。
- `DEFAULT_PART_SIZE`：分片缺省大小（5MB，S3 / MinIO 分片下限，末片除外）；
  `NULL_UPLOAD_ID`：占位上传会话标识前缀。
- `StoredObject` / `PresignedUrl`：对象元数据与预签名结果数据契约（frozen dataclass）。
- `MultipartInit` / `MultipartSession` / `MultipartPart` / `ExistingObjectRef`：分片上传参数对象、
  会话结果、分片结果与秒传命中引用（`BaseSchema`）。
- `BaseObjectStorage`：对象存储契约（`key = "object_storage"`）——异步 `put` / `get` / `delete` /
  `exists` / `presign`（预签名 URL 直连，后端不代理文件流）。
- `BaseMultipartUpload`：分片上传与秒传判定契约（`key = plugin_key = "multipart_upload"`）——异步
  `initiate` / `upload_part` / `complete` / `abort` / `check`。
- `get_object_storage` / `get_multipart_upload`：依赖注入提供者（应用级单例；公共依赖经
  `app/api/deps.py` 统一导出）。

口径：安全控制（类型白名单 / 大小上限 / SHA256 校验 / 租户配额联动）与上传下载 / 分片状态机、孤儿回收
归上层（文件管理阶段）；本契约只落**存储原语**与**分片托管 / 秒传判定**。`get` 供后端内部读取，
下载 / 预览走 `presign`；`get` 未命中抛 `NotFoundError`（与仓储统一不存在语义一致），`delete` 幂等；
分片上传会话幂等经幂等基座（`02-25`）承载、键由上层按 `bms:{租户}:files:{业务键}` 构造。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request
from pydantic import Field

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from app.schemas.base import BaseSchema

__all__ = [
    "DEFAULT_PART_SIZE",
    "DEFAULT_PRESIGN_TTL",
    "NULL_ETAG",
    "NULL_PRESIGNED_URL",
    "NULL_UPLOAD_ID",
    "STORAGE_BUCKET",
    "BaseMultipartUpload",
    "BaseObjectStorage",
    "ExistingObjectRef",
    "MultipartInit",
    "MultipartPart",
    "MultipartSession",
    "PresignedUrl",
    "StoredObject",
    "get_multipart_upload",
    "get_object_storage",
]

STORAGE_BUCKET = "bms-files"
"""默认私有桶名（《架构设计 · 文件管理》「安全控制」节）。"""

DEFAULT_PRESIGN_TTL = 3600
"""预签名 URL 默认有效期（秒，1 小时）。"""

NULL_ETAG = "null-etag"
"""占位对象 etag（NullObjectStorage.put 与占位分片固定返回）。"""

NULL_PRESIGNED_URL = "null-presigned-url"
"""占位预签名 URL（NullObjectStorage.presign 固定返回，便于断言）。"""

DEFAULT_PART_SIZE = 5 * 1024 * 1024
"""分片缺省大小（字节，5MB；S3 / MinIO 分片下限，末片除外）。"""

NULL_UPLOAD_ID = "null-upload-id"
"""占位上传会话标识前缀（占位实现前缀 + 递增序号，便于断言多会话并存）。"""


@dataclass(frozen=True)
class StoredObject(BaseObject):
    """对象元数据。"""

    key: str
    """对象 key。"""

    size: int
    """字节数。"""

    content_type: str | None = None
    """内容类型。"""

    etag: str | None = None
    """对象 etag。"""


@dataclass(frozen=True)
class PresignedUrl(BaseObject):
    """预签名结果。"""

    url: str
    """预签名 URL。"""

    expires_in: int
    """有效期（秒）。"""

    method: str = "GET"
    """HTTP 方法。"""


class MultipartInit(BaseSchema):
    """分片上传初始化参数对象（目标对象 key 由上层按对象 key 规范构造）。"""

    key: str = Field(description="目标对象 key（上层按 bms:{租户}:files:{业务键} 构造，基座透传）")
    size: int = Field(gt=0, description="文件字节数（须大于 0；空文件不走分片上传）")
    sha256: str = Field(min_length=1, description="整文件 SHA256（供秒传判定与合并校验）")
    mime: str | None = Field(default=None, description="内容类型（可空）")
    part_size: int | None = Field(default=None, gt=0, description="分片大小（字节）；缺省取 DEFAULT_PART_SIZE")


class MultipartSession(BaseSchema):
    """分片上传会话（初始化结果）。"""

    upload_id: str = Field(description="会话标识（后续分片 / 合并 / 取消均以它为准）")
    key: str = Field(description="目标对象 key（回显，供上层记录与合并校验）")
    part_size: int = Field(description="分片大小（字节）；末片可小于该值")
    total_parts: int = Field(description="分片总数（part_no 取值 1 ~ total_parts）")


class MultipartPart(BaseSchema):
    """分片上传结果（单分片元数据）。"""

    part_no: int = Field(ge=1, description="分片序号（从 1 起，S3 / MinIO 口径）")
    etag: str = Field(description="分片 etag（合并时按序号顺序提交）")
    size: int = Field(ge=0, description="分片字节数")


class ExistingObjectRef(BaseSchema):
    """秒传命中返回的既有对象引用（同内容不重传，直接复用该对象）。"""

    key: str = Field(description="既有对象 key")
    size: int = Field(ge=0, description="对象字节数")
    content_type: str | None = Field(default=None, description="内容类型")
    etag: str | None = Field(default=None, description="对象 etag")
    stored_at: datetime | None = Field(default=None, description="对象写入时间（供上层判定引用有效期 / 生命周期）")


class BaseObjectStorage(BasePluggable, ABC):
    """对象存储契约：写入 / 读取 / 删除 / 存在判定 / 预签名。"""

    key: str = "object_storage"
    plugin_key: str = "object_storage"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """写入对象。

        Args:
            key: 对象 key。
            data: 对象内容。
            content_type: 内容类型（可选）。

        Returns:
            StoredObject: 对象元数据。
        """

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """读取对象内容（后端内部使用）。

        Args:
            key: 对象 key。

        Returns:
            bytes: 对象内容。

        Raises:
            NotFoundError: 对象不存在（10002 / 404，全局处理器统一转响应）。
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除对象（幂等，不存在不报错）。

        Args:
            key: 对象 key。
        """

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """对象是否存在。

        Args:
            key: 对象 key。

        Returns:
            bool: 存在为 True。
        """

    @abstractmethod
    async def presign(
        self,
        key: str,
        *,
        method: str = "GET",
        expires_in: int = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUrl:
        """生成限时预签名 URL（下载 / 上传直连，后端不代理文件流）。

        Args:
            key: 对象 key。
            method: HTTP 方法（默认 GET）。
            expires_in: 有效期（秒，默认 `DEFAULT_PRESIGN_TTL`）。

        Returns:
            PresignedUrl: 预签名结果。
        """


class BaseMultipartUpload(BasePluggable, ABC):
    """分片上传契约：初始化 / 分片 / 合并 / 取消 / 秒传判定（分片状态机与孤儿回收归上层）。"""

    key: str = "multipart_upload"
    plugin_key: str = "multipart_upload"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def initiate(self, init: MultipartInit) -> MultipartSession:
        """初始化分片上传会话。

        Args:
            init: 初始化参数对象（目标对象 key / 字节数 / SHA256 / 内容类型 / 分片大小）。

        Returns:
            MultipartSession: 会话（`upload_id` / `key` / `part_size` / `total_parts`）。
        """

    @abstractmethod
    async def upload_part(self, upload_id: str, part_no: int, data: bytes) -> MultipartPart:
        """上传单个分片。

        Args:
            upload_id: 会话标识。
            part_no: 分片序号（从 1 起，取值 1 ~ `total_parts`）。
            data: 分片内容（末片可小于分片大小）。

        Returns:
            MultipartPart: 分片结果（`part_no` / `etag` / `size`）。

        Raises:
            NotFoundError: 会话不存在 / 分片序号越界（10002 / 404，全局处理器统一转响应）。
        """

    @abstractmethod
    async def complete(self, upload_id: str) -> StoredObject:
        """合并分片为最终对象。

        Args:
            upload_id: 会话标识。

        Returns:
            StoredObject: 合并产物元数据（落 `sys_file` 元数据与事件归上层）。

        Raises:
            NotFoundError: 会话不存在（10002 / 404）。
        """

    @abstractmethod
    async def abort(self, upload_id: str) -> None:
        """取消会话并清理临时分片（会话不存在抛 `NotFoundError`）。

        Args:
            upload_id: 会话标识。

        Raises:
            NotFoundError: 会话不存在（10002 / 404）。
        """

    @abstractmethod
    async def check(self, sha256: str, size: int) -> ExistingObjectRef | None:
        """秒传判定：同内容（校验值 + 大小）是否已有对象。

        Args:
            sha256: 整文件 SHA256。
            size: 文件字节数。

        Returns:
            ExistingObjectRef | None: 命中返回既有对象引用；未命中返回 None（是否复用由上层决定）。
        """


def get_object_storage(request: Request) -> BaseObjectStorage:
    """取应用级对象存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseObjectStorage: 应用装配的对象存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseObjectStorage",
        resolve_plugin(
            "object_storage",
            settings.storage.provider,
            expected_version=BaseObjectStorage.contract_version,
        ),
    )


def get_multipart_upload(request: Request) -> BaseMultipartUpload:
    """取应用级分片上传（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseMultipartUpload: 应用装配的分片上传实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseMultipartUpload",
        resolve_plugin(
            "multipart_upload",
            settings.multipart_upload.provider,
            expected_version=BaseMultipartUpload.contract_version,
        ),
    )
