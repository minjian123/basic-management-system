"""导入导出能力域 · 导入源文件端口（04_01）。

- `ImportSourceStore`：导入源文件读写删契约；默认实现落 `BaseObjectStorage`。
- `ObjectStorageImportSourceStore`：包装对象存储（`local` / `minio` 均可），不建 `sys_file` 元数据。
- `build_import_source_key`：对象 key 统一助手（`bms:{租户|global}:imports:source:{token}.xlsx`）。

口径：源文件由 API 落存储、作业读取后删除；端口抽象让后续切换到文件服务只换实现，编排零改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from bms_core.core.objects import BaseFrameworkObject
from bms_core.storage.base import BaseObjectStorage
from bms_core.transfer.openpyxl_io import XLSX_CONTENT_TYPE

__all__ = [
    "ImportSourceStore",
    "ObjectStorageImportSourceStore",
    "build_import_source_key",
]


def build_import_source_key(tenant: str | None, token: str) -> str:
    """构建导入源文件对象 key（路径风格，Windows 本地存储安全）。

    Args:
        tenant: 租户标识；None 为全局。
        token: 随机 token（不含路径分隔符）。

    Returns:
        str: 对象 key（`{tenant|global}/imports/source/{token}.xlsx`）。
    """
    scope = tenant or "global"
    return f"{scope}/imports/source/{token}.xlsx"


class ImportSourceStore(BaseFrameworkObject, ABC):
    """导入源文件存储契约。"""

    @abstractmethod
    async def put(self, key: str, data: bytes) -> None:
        """写入源文件。

        Args:
            key: 对象 key。
            data: 文件字节。
        """

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """读取源文件。

        Args:
            key: 对象 key。

        Returns:
            bytes: 文件字节。
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """删除源文件（幂等）。

        Args:
            key: 对象 key。
        """


class ObjectStorageImportSourceStore(ImportSourceStore):
    """对象存储实现：只存 xlsx 源文件，不建 `sys_file` 元数据。"""

    def __init__(self, storage: BaseObjectStorage) -> None:
        """初始化。

        Args:
            storage: 对象存储能力实现。
        """
        self._storage = storage

    async def put(self, key: str, data: bytes) -> None:
        """写入源文件。

        Args:
            key: 对象 key。
            data: 文件字节。
        """
        await self._storage.put(key, data, content_type=XLSX_CONTENT_TYPE)

    async def get(self, key: str) -> bytes:
        """读取源文件。

        Args:
            key: 对象 key。

        Returns:
            bytes: 文件字节。
        """
        return await self._storage.get(key)

    async def delete(self, key: str) -> None:
        """删除源文件（幂等）。

        Args:
            key: 对象 key。
        """
        await self._storage.delete(key)
