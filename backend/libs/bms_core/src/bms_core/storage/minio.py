"""storage 能力域：MinIO 实现（延迟导入 SDK；04-1-1）。

- 顶层**不**导入 SDK：客户端惰性构造（首次调用时 `from minio import Minio`），
  同步 SDK 调用统一 `asyncio.to_thread`。
- 端点 / 凭据取 `settings.minio`（密钥仅经环境变量注入，不落配置 / 日志 / 清单）；
  桶名取 `[storage].options.bucket`（缺省 `STORAGE_BUCKET`）。
- 语义：`get` 未命中 → `NotFoundError`；`delete` 幂等；`exists` 命中异常 → False；
  `presign` 按 `method` 分派 `presigned_get_object` / `presigned_put_object`。
- 工厂登记与启动校验（依赖 / 配置齐备，不连通）见 `app/core/assembly.py`。
"""

import asyncio
import hashlib
from datetime import timedelta
from typing import Any

from bms_core.core.exceptions import NotFoundError
from bms_core.storage.base import (
    DEFAULT_PRESIGN_TTL,
    STORAGE_BUCKET,
    BaseObjectStorage,
    PresignedUrl,
    StoredObject,
)

__all__ = ["MinioObjectStorage"]

_ETAG_LENGTH = 16
"""etag 取 SHA256 摘要前缀长度（十六进制字符数；与本地实现口径一致）。"""


class MinioObjectStorage(BaseObjectStorage):
    """MinIO 对象存储：SDK 惰性导入与惰性客户端。"""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = STORAGE_BUCKET,
        secure: bool = False,
    ) -> None:
        """初始化（不导入 SDK、不建连）。

        Args:
            endpoint: MinIO 端点（host:port）。
            access_key: 访问密钥。
            secret_key: 私钥（仅内存持有，不落盘 / 不入日志）。
            bucket: 桶名。
            secure: 是否 HTTPS。
        """
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._client: Any = None

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """写入对象。

        Args:
            key: 对象 key。
            data: 对象内容。
            content_type: 内容类型（可选）。

        Returns:
            StoredObject: 对象元数据（etag 取内容 SHA256 摘要前缀）。
        """
        client = self._ensure_client()
        await asyncio.to_thread(self._put_sync, client, key, data, content_type)
        return StoredObject(
            key=key,
            size=len(data),
            content_type=content_type,
            etag=hashlib.sha256(data).hexdigest()[:_ETAG_LENGTH],
        )

    async def get(self, key: str) -> bytes:
        """读取对象内容。

        Args:
            key: 对象 key。

        Returns:
            bytes: 对象内容。

        Raises:
            NotFoundError: 对象不存在。
        """
        client = self._ensure_client()
        return await asyncio.to_thread(self._get_sync, client, key)

    async def delete(self, key: str) -> None:
        """删除对象（幂等，不存在不报错）。

        Args:
            key: 对象 key。
        """
        client = self._ensure_client()
        await asyncio.to_thread(self._delete_sync, client, key)

    async def exists(self, key: str) -> bool:
        """对象是否存在。

        Args:
            key: 对象 key。

        Returns:
            bool: 存在为 True。
        """
        client = self._ensure_client()
        return await asyncio.to_thread(self._exists_sync, client, key)

    async def presign(
        self,
        key: str,
        *,
        method: str = "GET",
        expires_in: int = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUrl:
        """生成预签名 URL（GET / PUT 分派）。

        Args:
            key: 对象 key。
            method: HTTP 方法（`GET` / `PUT`；其余按 `GET` 处理）。
            expires_in: 有效期（秒）。

        Returns:
            PresignedUrl: 预签名结果。
        """
        client = self._ensure_client()
        expires = timedelta(seconds=expires_in)
        if method.upper() == "PUT":
            url = await asyncio.to_thread(client.presigned_put_object, self._bucket, key, expires)
        else:
            url = await asyncio.to_thread(client.presigned_get_object, self._bucket, key, expires)
        return PresignedUrl(url=str(url), expires_in=expires_in, method=method)

    def _ensure_client(self) -> Any:
        """惰性导入 SDK 并构造客户端（不建连）。

        Returns:
            Any: MinIO 客户端实例（SDK 私有类型不在契约面暴露）。
        """
        if self._client is None:
            from minio import Minio

            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
        return self._client

    def _put_sync(self, client: Any, key: str, data: bytes, content_type: str | None) -> None:
        """同步写入（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。
            data: 对象内容。
            content_type: 内容类型（可选）。
        """
        from io import BytesIO

        client.put_object(self._bucket, key, BytesIO(data), len(data), content_type=content_type)

    def _get_sync(self, client: Any, key: str) -> bytes:
        """同步读取（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。

        Returns:
            bytes: 对象内容。

        Raises:
            NotFoundError: 对象不存在。
        """
        from minio.error import S3Error

        try:
            response = client.get_object(self._bucket, key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise NotFoundError(f"对象不存在：{key}") from exc
            raise
        try:
            return bytes(response.read())
        finally:
            response.close()
            response.release_conn()

    def _delete_sync(self, client: Any, key: str) -> None:
        """同步删除（幂等；线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。
        """
        from minio.error import S3Error

        try:
            client.remove_object(self._bucket, key)
        except S3Error as exc:
            if exc.code != "NoSuchKey":
                raise

    def _exists_sync(self, client: Any, key: str) -> bool:
        """同步存在判定（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。

        Returns:
            bool: 存在为 True。
        """
        from minio.error import S3Error

        try:
            client.stat_object(self._bucket, key)
        except S3Error:
            return False
        return True
