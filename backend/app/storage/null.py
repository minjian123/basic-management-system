"""storage 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.storage.base.py 迁入）。"""

from app.core.capability import BaseNullObject
from app.storage.base import (
    DEFAULT_PRESIGN_TTL,
    NULL_ETAG,
    NULL_PRESIGNED_URL,
    BaseObjectStorage,
    PresignedUrl,
    StoredObject,
)

__all__ = [
    "NullObjectStorage",
]


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
