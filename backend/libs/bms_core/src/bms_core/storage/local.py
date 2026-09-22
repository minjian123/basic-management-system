"""storage 能力域：本地文件系统实现（真实读写；04-1）。

- `LocalObjectStorage`：键经安全校验（拒绝空 / 绝对路径 / `..`）后映射到根目录下相对路径；
  写入走「临时文件 + `os.replace`」原子写；阻塞 IO 统一 `asyncio.to_thread`（不阻塞事件循环）。
- 根目录经 `[storage].options.root` 注入（缺省 `var/storage`；`BMS_STORAGE__OPTIONS__ROOT` 可覆盖）；
  `__init__` 不建目录，写入路径按需创建。
- `presign` 返回 `file://` 绝对路径 URI（本地实现无远端直连；消费方仍走统一契约）。
"""

import asyncio
import hashlib
import os
from pathlib import Path, PurePosixPath

from bms_core.core.exceptions import NotFoundError
from bms_core.storage.base import DEFAULT_PRESIGN_TTL, BaseObjectStorage, PresignedUrl, StoredObject

__all__ = ["DEFAULT_ROOT", "LocalObjectStorage"]

DEFAULT_ROOT = "var/storage"
"""本地存储根目录缺省值（相对运行目录；仓库根 `var/` 已 gitignore）。"""

_ETAG_LENGTH = 16
"""本地 etag 取 SHA256 摘要前缀长度（十六进制字符数）。"""


class LocalObjectStorage(BaseObjectStorage):
    """本地文件系统对象存储：真实读写（零外部依赖）。"""

    def __init__(self, *, root: str | Path = DEFAULT_ROOT) -> None:
        """初始化。

        Args:
            root: 存储根目录（不存在时于写入路径按需创建）。
        """
        self._root = Path(root)

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        """写入对象（原子写：临时文件 + `os.replace`）。

        Args:
            key: 对象 key。
            data: 对象内容。
            content_type: 内容类型（可选）。

        Returns:
            StoredObject: 对象元数据（etag 取内容 SHA256 摘要前缀）。

        Raises:
            ValueError: 对象 key 非法（空 / 绝对路径 / 含 `..`）。
        """
        path = self._resolve(key)
        await asyncio.to_thread(self._write_atomic, path, data)
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
            ValueError: 对象 key 非法。
        """
        path = self._resolve(key)
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError as exc:
            raise NotFoundError(f"对象不存在：{key}") from exc

    async def delete(self, key: str) -> None:
        """删除对象（幂等，不存在不报错）。

        Args:
            key: 对象 key。
        """
        path = self._resolve(key)
        await asyncio.to_thread(path.unlink, True)

    async def exists(self, key: str) -> bool:
        """对象是否存在。

        Args:
            key: 对象 key。

        Returns:
            bool: 存在为 True。
        """
        path = self._resolve(key)
        return await asyncio.to_thread(path.is_file)

    async def presign(
        self,
        key: str,
        *,
        method: str = "GET",
        expires_in: int = DEFAULT_PRESIGN_TTL,
    ) -> PresignedUrl:
        """生成 `file://` 绝对路径 URI（本地实现无远端直连）。

        Args:
            key: 对象 key。
            method: HTTP 方法（本地实现透传）。
            expires_in: 有效期（本地实现透传）。

        Returns:
            PresignedUrl: 本地文件 URI。
        """
        path = self._resolve(key)
        absolute = await asyncio.to_thread(path.resolve)
        return PresignedUrl(url=absolute.as_uri(), expires_in=expires_in, method=method)

    def _resolve(self, key: str) -> Path:
        """键安全校验并映射为根目录下路径。

        Args:
            key: 对象 key。

        Returns:
            Path: 目标文件路径。

        Raises:
            ValueError: 对象 key 非法（空 / 绝对路径 / 含 `..`）。
        """
        candidate = PurePosixPath(key)
        if not key or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"非法对象 key：{key!r}")
        return self._root.joinpath(*candidate.parts)

    def _write_atomic(self, path: Path, data: bytes) -> None:
        """原子写（同目录临时文件 + `os.replace`）。

        Args:
            path: 目标文件路径。
            data: 对象内容。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
