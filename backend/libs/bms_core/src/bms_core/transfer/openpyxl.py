"""导入导出能力域 · openpyxl 真实导入实现（04_01）。

- `OpenpyxlImporter`（插件名 `openpyxl`）：`parse_rows` 读取「数据」sheet；`validate_rows` 做通用
  必填 / 长度 / 类型 / 正则 / 可选值校验；业务字段值域与唯一性由业务定义负责。
- 所有 openpyxl 读写经 `asyncio.to_thread`，不阻塞事件循环。
- xlsx 结构 / zip 安全边界取 `ImportLimits` 代码默认；调用方（导入编排）另按租户参数做文件大小 /
  行数预检，二者不冲突。
"""

from __future__ import annotations

import asyncio

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.importer import (
    BaseImporter,
    ImportResult,
    ParsedRow,
    validate_rows_common,
)
from bms_core.transfer.limits import (
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_ZIP_ENTRIES,
    ImportLimits,
)
from bms_core.transfer.openpyxl_io import DATA_SHEET_NAME, read_sheet_rows

__all__ = ["OpenpyxlImporter"]


class OpenpyxlImporter(BaseImporter):
    """openpyxl 真实导入器：xlsx 解析 + 通用行校验。"""

    # 由 `core/assembly.py` 的显式工厂登记为 `importer:openpyxl`；置空避免 `__init_subclass__` 自动登记重名。
    plugin_name = ""

    def __init__(
        self,
        *,
        max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
        max_zip_entries: int = DEFAULT_MAX_ZIP_ENTRIES,
    ) -> None:
        """初始化。

        Args:
            max_uncompressed_bytes: 解压后总大小上限（字节）。
            max_zip_entries: zip 条目数上限。
        """
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_zip_entries = max_zip_entries

    @classmethod
    def from_limits(cls, limits: ImportLimits) -> OpenpyxlImporter:
        """按租户参数构造（可选；插件工厂缺省用代码默认）。

        Args:
            limits: 导入生效参数。

        Returns:
            OpenpyxlImporter: 导入器实例。
        """
        return cls(
            max_uncompressed_bytes=limits.max_uncompressed_bytes,
            max_zip_entries=limits.max_zip_entries,
        )

    async def parse_rows(
        self, data: bytes, *, columns: ConcurrentStableList[ColumnSpec]
    ) -> ConcurrentStableList[ParsedRow]:
        """解析 xlsx「数据」sheet 为带行号的行。

        Args:
            data: 文件字节。
            columns: 列定义。

        Returns:
            ConcurrentStableList[ParsedRow]: 数据行。

        Raises:
            XlsxInvalidFileError: 文件非法 / 无数据行。
            XlsxTemplateMismatchError: sheet 缺失 / 表头不匹配。
        """
        return await asyncio.to_thread(
            read_sheet_rows,
            data,
            sheet_name=DATA_SHEET_NAME,
            columns=columns,
            max_uncompressed_bytes=self._max_uncompressed_bytes,
            max_zip_entries=self._max_zip_entries,
        )

    async def validate_rows(
        self,
        rows: ConcurrentStableList[ParsedRow],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> ImportResult:
        """通用行校验（必填 / 长度 / 类型 / 正则 / 可选值）。

        Args:
            rows: 原始行。
            columns: 列定义。

        Returns:
            ImportResult: 有效行与错误回执。
        """
        return await validate_rows_common(rows, columns=columns)
