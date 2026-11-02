"""导入导出能力域 · 导出产物端口与对象 key 助手（04_02）。

- `build_export_object_key`：产物 key 统一助手（路径风格，Windows 本地存储安全）。
- `ExportArtifactStore`：产物写入 / 限时取址 / 删除契约；默认实现包 `BaseObjectStorage`。
- `ObjectStorageExportArtifactStore`：不建 `sys_file` 元数据、不占文件配额（与导入源文件同口径）。

口径：产物一律由编排层经本端口落对象存储，业务与路由不得自拼 key；删除幂等（不存在不报错），
过期清理由 `platform.export.cleanup` 作业按作业结果里的 key 回销。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.storage.base import BaseObjectStorage, PresignedUrl

__all__ = [
    "EXPORT_ARTIFACT_EXTS",
    "ExportArtifactStore",
    "ObjectStorageExportArtifactStore",
    "build_export_object_key",
]

EXPORT_ARTIFACT_EXTS: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("xlsx", "pdf"))
"""导出产物扩展名（与内容类型配对校验）。"""


def build_export_object_key(tenant: str | None, biz: str, token: str, ext: str) -> str:
    """构建导出产物对象 key（`{tenant|global}/exports/{biz}/{token}.{ext}`）。

    Args:
        tenant: 租户标识；None 为全局。
        biz: 业务标识（路径段）。
        token: 随机 token（不含路径分隔符）。
        ext: 扩展名（取值 ∈ `EXPORT_ARTIFACT_EXTS`）。

    Returns:
        str: 对象 key。

    Raises:
        ParamError: 扩展名不在白名单（`10001`，属编码错误）。
    """
    if ext not in EXPORT_ARTIFACT_EXTS:
        raise ParamError(f"导出产物扩展名非法：{ext}")
    scope = tenant or "global"
    return f"{scope}/exports/{biz}/{token}.{ext}"


class ExportArtifactStore(BaseFrameworkObject, ABC):
    """导出产物存储契约（写入 / 限时取址 / 删除）。"""

    @abstractmethod
    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """写入产物。

        Args:
            key: 对象 key。
            data: 产物字节。
            content_type: 内容类型。
        """

    @abstractmethod
    async def presign(self, key: str, *, expires_in: int) -> PresignedUrl:
        """生成限时取址。

        Args:
            key: 对象 key。
            expires_in: 有效期（秒）。

        Returns:
            PresignedUrl: 预签名结果。
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除产物（幂等）。

        Args:
            key: 对象 key。
        """


class ObjectStorageExportArtifactStore(ExportArtifactStore):
    """对象存储实现（不建 `sys_file` 元数据、不占文件配额）。"""

    def __init__(self, storage: BaseObjectStorage) -> None:
        """初始化。

        Args:
            storage: 对象存储能力实现。
        """
        self._storage = storage

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """写入产物。

        Args:
            key: 对象 key。
            data: 产物字节。
            content_type: 内容类型。
        """
        await self._storage.put(key, data, content_type=content_type)

    async def presign(self, key: str, *, expires_in: int) -> PresignedUrl:
        """生成限时取址。

        Args:
            key: 对象 key。
            expires_in: 有效期（秒）。

        Returns:
            PresignedUrl: 预签名结果。
        """
        return await self._storage.presign(key, expires_in=expires_in)

    async def delete(self, key: str) -> None:
        """删除产物（幂等）。

        Args:
            key: 对象 key。
        """
        await self._storage.delete(key)
