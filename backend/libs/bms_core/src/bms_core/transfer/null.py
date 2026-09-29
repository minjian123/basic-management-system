"""transfer 能力域缺省实现（Null Object）：占位返回、无副作用
（02-3 自 bms_core.transfer.exporter.py、bms_core.transfer.importer.py 迁入）。"""

from collections.abc import AsyncIterator

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.transfer.base import ColumnSpec
from bms_core.transfer.exporter import BaseExporter
from bms_core.transfer.importer import BaseImporter, ImportResult

__all__ = [
    "NullExporter",
    "NullImporter",
]


class _EmptyExporterStream(BaseFrameworkObject):
    """占位导出流：不产出任何分块。"""

    def __aiter__(self) -> _EmptyExporterStream:
        """进入异步迭代。

        Returns:
            _EmptyExporterStream: 自身。
        """
        return self

    async def __anext__(self) -> bytes:
        """结束迭代（无分块）。

        Raises:
            StopAsyncIteration: 立即结束。
        """
        raise StopAsyncIteration


class NullExporter(BaseExporter, BaseNullObject):
    """占位导出器：空流（不写文件，未接入真实实现时使用）。"""

    def export(
        self,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> AsyncIterator[bytes]:
        """返回空异步迭代流。

        Args:
            rows: 数据行（占位忽略）。
            columns: 列定义（占位忽略）。

        Returns:
            AsyncIterator[bytes]: 空流（无分块）。
        """
        return _EmptyExporterStream()


class NullImporter(BaseImporter, BaseNullObject):
    """占位导入器：空行 / 空结果（不读写文件，未接入真实实现时使用）。"""

    async def parse(
        self, data: bytes, *, columns: ConcurrentStableList[ColumnSpec]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """返回空行。

        Args:
            data: 文件字节（占位忽略）。
            columns: 列定义（占位忽略）。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 空集合。
        """
        return ConcurrentStableList()

    async def validate(
        self,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> ImportResult:
        """返回空结果。

        Args:
            rows: 原始行（占位忽略）。
            columns: 列定义（占位忽略）。

        Returns:
            ImportResult: 空结果（无有效行 / 无错误）。
        """
        return ImportResult(rows=(), errors=())
