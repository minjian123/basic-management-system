"""导入导出能力域 · 导出器真实实现（openpyxl，04_02）。

- `OpenpyxlExporter`（插件名 `openpyxl`，由 `core/assembly.py` 的显式工厂登记）：按列定义把行集写成
  单 sheet xlsx，并按固定块大小分块产出字节。
- 生成与分块：`build_export_workbook` 是同步纯函数（write_only 低内存），经 `asyncio.to_thread`
  执行；内存上界为完整文件（5000 行约 1~3MB），分块只为满足「流式产出」契约语义。

口径：脱敏在调用方完成（`bms_core.transfer.masking.mask_rows`），导出契约不内置脱敏；行形态为
`{列键: 已格式化值}`，业务格式化由导出定义负责。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.exporter import BaseExporter
from bms_core.transfer.openpyxl_io import build_export_workbook

__all__ = ["EXPORT_CHUNK_SIZE", "OpenpyxlExporter"]

EXPORT_CHUNK_SIZE = 64 * 1024
"""导出字节分块大小（64KB）。"""


class OpenpyxlExporter(BaseExporter):
    """openpyxl 真实导出器：列定义 + 行集 → xlsx 字节分块。"""

    # 由 `core/assembly.py` 的显式工厂登记为 `exporter:openpyxl`；置空避免 `__init_subclass__` 自动登记重名。
    plugin_name = ""

    def export(
        self,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> AsyncIterator[bytes]:
        """按列定义流式写出（分块产出字节）。

        Args:
            rows: 数据行（列键 → 值）。
            columns: 列定义（列序与表头）。

        Returns:
            AsyncIterator[bytes]: 字节分块异步迭代器。
        """
        return self._stream(rows, columns)

    async def _stream(
        self,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        columns: ConcurrentStableList[ColumnSpec],
    ) -> AsyncIterator[bytes]:
        """生成工作簿并分块产出。

        Args:
            rows: 数据行。
            columns: 列定义。

        Yields:
            bytes: 字节分块。
        """
        data = await asyncio.to_thread(build_export_workbook, columns, rows)
        for start in range(0, len(data), EXPORT_CHUNK_SIZE):
            yield data[start : start + EXPORT_CHUNK_SIZE]
