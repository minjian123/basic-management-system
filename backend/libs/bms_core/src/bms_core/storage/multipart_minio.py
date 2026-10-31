"""分片上传 · MinIO 实现（`minio`；03_01）。

- 分片作为独立对象写 `{object_key}.part.00001`；`complete` 用服务端**组合对象**
  （`compose_object`，S3 multipart copy），不把内容拉回应用进程；组合后按需流式复算 SHA256
  （`verify_sha256` 开启时读回一次，`_CHUNK_SIZE` 分块，不整份入内存），再删分片。
- SDK 顶层**不**导入（惰性构造）；同步调用统一 `asyncio.to_thread`。
- 端点 / 凭据取 `settings.minio`，桶名取 `[storage].options.bucket`（与对象存储实现同源）。
"""

import asyncio
import hashlib
from io import BytesIO
from typing import Any

from bms_core.core.exceptions import FileSizeExceededError, NotFoundError
from bms_core.storage.base import DEFAULT_PART_SIZE, STORAGE_BUCKET, StoredObject
from bms_core.storage.multipart import StorageMultipartUpload, UploadSession, UploadSessionStore, part_key

__all__ = ["ETAG_LENGTH", "MinioMultipartUpload"]

ETAG_LENGTH = 16
"""etag 取 SHA256 摘要前缀长度（十六进制字符数；与 MinIO 对象存储实现同口径）。"""

_CHUNK_SIZE = 1024 * 1024
"""流式复算 SHA256 的块大小（字节）。"""


class MinioMultipartUpload(StorageMultipartUpload):
    """MinIO 分片上传：分片落对象，合并走服务端组合。"""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = STORAGE_BUCKET,
        secure: bool = False,
        part_size: int = DEFAULT_PART_SIZE,
        max_parts: int = 10000,
        session_ttl_seconds: int = 86400,
        verify_sha256: bool = True,
        store: UploadSessionStore | None = None,
    ) -> None:
        """初始化（不导入 SDK、不建连）。

        Args:
            endpoint: MinIO 端点（host:port）。
            access_key: 访问密钥。
            secret_key: 私钥（仅内存持有）。
            bucket: 桶名。
            secure: 是否 HTTPS。
            part_size: 缺省分片大小（字节）。
            max_parts: 单文件分片数上限。
            session_ttl_seconds: 会话有效期（秒）。
            verify_sha256: 合并后是否复算整文件 SHA256。
            store: 会话存储（测试注入）。
        """
        super().__init__(
            part_size=part_size,
            max_parts=max_parts,
            session_ttl_seconds=session_ttl_seconds,
            verify_sha256=verify_sha256,
            store=store,
        )
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._secure = secure
        self._client: Any = None

    async def _write_part(self, object_key: str, part_no: int, data: bytes) -> str:
        """写入分片对象。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
            data: 分片内容。

        Returns:
            str: 分片 etag。
        """
        client = self._ensure_client()
        return await asyncio.to_thread(self._put_part_sync, client, part_key(object_key, part_no), data)

    async def _part_size(self, object_key: str, part_no: int) -> int | None:
        """取分片对象字节数（不存在返回 None）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。

        Returns:
            int | None: 字节数；不存在为 None。
        """
        client = self._ensure_client()
        return await asyncio.to_thread(self._stat_sync, client, part_key(object_key, part_no))

    async def _compose(self, session: UploadSession) -> StoredObject:
        """服务端组合分片为最终对象（按需复算整文件 SHA256）。

        Args:
            session: 会话。

        Returns:
            StoredObject: 合并产物元数据。

        Raises:
            FileSizeExceededError: 分片数超过组合上限。
            NotFoundError: 组合后对象缺失。
        """
        if session.total_parts > self._max_parts:
            raise FileSizeExceededError(f"分片数超过组合上限：{session.total_parts} > {self._max_parts}")
        client = self._ensure_client()
        await asyncio.to_thread(self._compose_sync, client, session)
        if self._verify_sha256:
            await self._verify_object_sha256(session.key, session.sha256)
        for part_no in range(1, session.total_parts + 1):
            await self._delete_part(session.key, part_no)
        return StoredObject(
            key=session.key,
            size=session.size,
            content_type=session.mime,
            etag=session.sha256[:ETAG_LENGTH],
        )

    async def _delete_part(self, object_key: str, part_no: int) -> None:
        """删除分片对象（不存在不报错）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
        """
        client = self._ensure_client()
        await asyncio.to_thread(self._remove_sync, client, part_key(object_key, part_no))

    async def _sha256_of(self, object_key: str) -> str:
        """流式复算对象 SHA256。

        Args:
            object_key: 对象 key。

        Returns:
            str: 十六进制摘要。

        Raises:
            NotFoundError: 对象不存在。
        """
        client = self._ensure_client()
        return await asyncio.to_thread(self._hash_sync, client, object_key)

    async def _delete_object(self, object_key: str) -> None:
        """删除最终对象（幂等）。

        Args:
            object_key: 对象 key。
        """
        client = self._ensure_client()
        await asyncio.to_thread(self._remove_sync, client, object_key)

    def _ensure_client(self) -> Any:
        """惰性导入 SDK 并构造客户端（不建连）。

        Returns:
            Any: MinIO 客户端实例。
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

    def _put_part_sync(self, client: Any, key: str, data: bytes) -> str:
        """同步写分片对象（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 分片对象 key。
            data: 分片内容。

        Returns:
            str: 分片 etag（SDK 返回值；缺失时回落到内容摘要）。
        """
        result = client.put_object(self._bucket, key, BytesIO(data), len(data))
        etag = getattr(result, "etag", None)
        return str(etag) if etag else hashlib.sha256(data).hexdigest()[:ETAG_LENGTH]

    def _stat_sync(self, client: Any, key: str) -> int | None:
        """同步取对象字节数（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。

        Returns:
            int | None: 字节数；不存在为 None。
        """
        from minio.error import S3Error

        try:
            stat = client.stat_object(self._bucket, key)
        except S3Error:
            return None
        return int(stat.size)

    def _compose_sync(self, client: Any, session: UploadSession) -> None:
        """同步服务端组合（线程内执行）。

        Args:
            client: MinIO 客户端。
            session: 会话。
        """
        from minio.commonconfig import ComposeSource

        sources = [
            ComposeSource(self._bucket, part_key(session.key, part_no)) for part_no in range(1, session.total_parts + 1)
        ]
        metadata = None if session.mime is None else {"Content-Type": session.mime}
        client.compose_object(self._bucket, session.key, sources, metadata=metadata)

    def _remove_sync(self, client: Any, key: str) -> None:
        """同步删除对象（幂等；线程内执行）。

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

    def _hash_sync(self, client: Any, key: str) -> str:
        """同步流式复算对象 SHA256（线程内执行）。

        Args:
            client: MinIO 客户端。
            key: 对象 key。

        Returns:
            str: 十六进制摘要。

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
        digest = hashlib.sha256()
        try:
            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            response.close()
            response.release_conn()
        return digest.hexdigest()
