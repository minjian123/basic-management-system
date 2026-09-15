"""文件存储能力域：对象存储基座契约（真实 MinIO / 本地文件系统随文件管理阶段回补）。

- `STORAGE_BUCKET`：默认私有桶名（`bms-files`）；`DEFAULT_PRESIGN_TTL`：预签名默认有效期（秒，1 小时）。
- `StoredObject` / `PresignedUrl`：对象元数据与预签名结果数据契约（frozen dataclass）。
- `BaseObjectStorage`：能力域中间层契约（`key = "object_storage"`）——异步 `put` / `get` / `delete` /
  `exists` / `presign`（预签名 URL 直连，后端不代理文件流）。
- `NullObjectStorage`：占位实现——固定返回（**不连 MinIO、不落盘**）。
- `get_object_storage`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：安全控制（类型白名单 / 大小上限 / SHA256 校验 / 租户配额联动）与上传下载 / 分片状态机归上层
（文件管理阶段）；本契约只落存储原语。`get` 供后端内部读取，下载 / 预览走 `presign`；
`get` 未命中抛 `NotFoundError`（与仓储统一不存在语义一致），`delete` 幂等。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseNullObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "DEFAULT_PRESIGN_TTL",
    "NULL_ETAG",
    "NULL_PRESIGNED_URL",
    "STORAGE_BUCKET",
    "BaseObjectStorage",
    "NullObjectStorage",
    "PresignedUrl",
    "StoredObject",
    "get_object_storage",
]

STORAGE_BUCKET = "bms-files"
"""默认私有桶名（《架构设计 · 文件管理》「安全控制」节）。"""

DEFAULT_PRESIGN_TTL = 3600
"""预签名 URL 默认有效期（秒，1 小时）。"""

NULL_ETAG = "null-etag"
"""占位对象 etag（NullObjectStorage.put 固定返回）。"""

NULL_PRESIGNED_URL = "null-presigned-url"
"""占位预签名 URL（NullObjectStorage.presign 固定返回，便于断言）。"""


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


class NullObjectStorage(BaseObjectStorage, BaseNullObject):
    """占位对象存储：固定返回（不连 MinIO、不落盘，未接入真实实现时使用）。"""

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """回显对象元数据（占位不写入）。

        Args:
            key: 对象 key（占位透传）。
            data: 对象内容（占位不落盘，仅取长度）。
            content_type: 内容类型（占位透传）。

        Returns:
            StoredObject: 对象元数据（etag 为 `NULL_ETAG`）。
        """
        return StoredObject(key=key, size=len(data), content_type=content_type, etag=NULL_ETAG)

    async def get(self, key: str) -> bytes:
        """返回空字节（占位不读取）。

        Args:
            key: 对象 key（占位忽略）。

        Returns:
            bytes: 空字节。
        """
        return b""

    async def delete(self, key: str) -> None:
        """空操作（占位不删除）。

        Args:
            key: 对象 key（占位忽略）。
        """

    async def exists(self, key: str) -> bool:
        """恒定存在。

        Args:
            key: 对象 key（占位忽略）。

        Returns:
            bool: True。
        """
        return True

    async def presign(
        self,
        key: str,
        *,
        method: str = "GET",
        expires_in: int = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUrl:
        """固定返回预签名结果。

        Args:
            key: 对象 key（占位忽略）。
            method: HTTP 方法（占位透传）。
            expires_in: 有效期（占位透传）。

        Returns:
            PresignedUrl: 占位预签名结果（url 为 `NULL_PRESIGNED_URL`）。
        """
        return PresignedUrl(url=NULL_PRESIGNED_URL, expires_in=expires_in, method=method)


def get_object_storage(request: Request) -> BaseObjectStorage:
    """取应用级对象存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseObjectStorage: 应用装配的对象存储实例。
    """
    return cast("BaseObjectStorage", request.app.state.object_storage)
