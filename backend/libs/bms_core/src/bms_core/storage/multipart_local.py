"""分片上传 · 本地文件系统实现（`local`；03_01）。

- 分片落盘为 `<root>/<object_key>.part.00001` 普通文件；`complete` 按序**流式拼接**到同目录临时文件
  （边写边算 SHA256，内存占用 O(64KB)），校验通过后 `os.replace` 原子落位，再删分片。
- 与 `LocalObjectStorage` 共用根目录解析（`path_of`），保证「分片 key / 最终对象 key」落在同一空间。
- 阻塞 IO 一律 `asyncio.to_thread`（不阻塞事件循环）。
"""

import asyncio
import hashlib
import os
from pathlib import Path

from bms_core.core.exceptions import FileChecksumMismatchError, NotFoundError
from bms_core.storage.base import DEFAULT_PART_SIZE, StoredObject
from bms_core.storage.local import DEFAULT_ROOT, LocalObjectStorage
from bms_core.storage.multipart import StorageMultipartUpload, UploadSession, UploadSessionStore, part_key

__all__ = ["ETAG_LENGTH", "LocalMultipartUpload"]

ETAG_LENGTH = 16
"""etag 取 SHA256 摘要前缀长度（十六进制字符数；与 `LocalObjectStorage` 同口径）。"""

_CHUNK_SIZE = 64 * 1024
"""流式拼接 / 复算的块大小（字节）。"""


class LocalMultipartUpload(StorageMultipartUpload):
    """本地文件系统分片上传：分片落文件，合并为流式拼接。"""

    def __init__(
        self,
        *,
        root: str | Path = DEFAULT_ROOT,
        part_size: int = DEFAULT_PART_SIZE,
        max_parts: int = 10000,
        session_ttl_seconds: int = 86400,
        verify_sha256: bool = True,
        store: UploadSessionStore | None = None,
    ) -> None:
        """初始化。

        Args:
            root: 存储根目录（与 `[storage].options.root` 同源）。
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
        self._storage = LocalObjectStorage(root=root)

    async def _write_part(self, object_key: str, part_no: int, data: bytes) -> str:
        """写入分片文件（原子写）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
            data: 分片内容。

        Returns:
            str: 分片 etag。
        """
        path = self._part_path(object_key, part_no)
        await asyncio.to_thread(self._write_bytes, path, data)
        return hashlib.sha256(data).hexdigest()[:ETAG_LENGTH]

    async def _part_size(self, object_key: str, part_no: int) -> int | None:
        """取分片字节数。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。

        Returns:
            int | None: 字节数；不存在为 None。
        """
        path = self._part_path(object_key, part_no)
        if not await asyncio.to_thread(path.is_file):
            return None
        return await asyncio.to_thread(lambda: path.stat().st_size)

    async def _compose(self, session: UploadSession) -> StoredObject:
        """流式拼接分片为最终对象（按需复算整文件 SHA256）。

        Args:
            session: 会话。

        Returns:
            StoredObject: 合并产物元数据。

        Raises:
            NotFoundError: 合并后对象缺失（并发清理）。
        """
        final = self._storage.path_of(session.key)
        digest = await asyncio.to_thread(self._concat, session)
        if self._verify_sha256 and digest != session.sha256:
            await asyncio.to_thread(final.unlink, True)
            raise FileChecksumMismatchError(f"整文件校验失败：sha256 {digest} != 声明 {session.sha256}")
        for part_no in range(1, session.total_parts + 1):
            await self._delete_part(session.key, part_no)
        return StoredObject(
            key=session.key,
            size=session.size,
            content_type=session.mime,
            etag=digest[:ETAG_LENGTH],
        )

    async def _delete_part(self, object_key: str, part_no: int) -> None:
        """删除分片文件（不存在不报错）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。
        """
        await asyncio.to_thread(self._part_path(object_key, part_no).unlink, True)

    async def _sha256_of(self, object_key: str) -> str:
        """流式复算对象 SHA256。

        Args:
            object_key: 对象 key。

        Returns:
            str: 十六进制摘要。

        Raises:
            NotFoundError: 对象不存在。
        """
        path = self._storage.path_of(object_key)
        try:
            return await asyncio.to_thread(self._hash_file, path)
        except OSError as exc:
            raise NotFoundError(f"对象不存在：{object_key}") from exc

    async def _delete_object(self, object_key: str) -> None:
        """删除最终对象（幂等）。

        Args:
            object_key: 对象 key。
        """
        await asyncio.to_thread(self._storage.path_of(object_key).unlink, True)

    def _part_path(self, object_key: str, part_no: int) -> Path:
        """分片文件路径（复用对象存储的 key 安全校验与根目录映射）。

        Args:
            object_key: 目标对象 key。
            part_no: 分片序号。

        Returns:
            Path: 分片文件路径。
        """
        return self._storage.path_of(part_key(object_key, part_no))

    @staticmethod
    def _write_bytes(path: Path, data: bytes) -> None:
        """原子写字节（同目录临时文件 + `os.replace`）。

        Args:
            path: 目标路径。
            data: 内容。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _concat(self, session: UploadSession) -> str:
        """按序流式拼接分片（返回整文件 SHA256）。

        Args:
            session: 会话。

        Returns:
            str: 整文件 SHA256（十六进制）。

        Raises:
            NotFoundError: 存在缺失分片。
        """
        final = self._storage.path_of(session.key)
        final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.with_name(f".{final.name}.merge-{os.getpid()}")
        digest = hashlib.sha256()
        try:
            with temporary.open("wb") as sink:
                for part_no in range(1, session.total_parts + 1):
                    source = self._part_path(session.key, part_no)
                    if not source.is_file():
                        raise NotFoundError(f"分片缺失：{part_no}")
                    with source.open("rb") as handle:
                        while chunk := handle.read(_CHUNK_SIZE):
                            digest.update(chunk)
                            sink.write(chunk)
            os.replace(temporary, final)
        finally:
            temporary.unlink(missing_ok=True)
        return digest.hexdigest()

    @staticmethod
    def _hash_file(path: Path) -> str:
        """流式计算文件 SHA256。

        Args:
            path: 文件路径。

        Returns:
            str: 十六进制摘要。
        """
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                digest.update(chunk)
        return digest.hexdigest()
