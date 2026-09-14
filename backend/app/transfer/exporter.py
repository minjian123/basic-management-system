"""导入导出能力域 · 导出：列定义 / 流式写出契约（真实 openpyxl 随通用能力阶段回补）。

- `BaseExporter`：能力域中间层契约（`key = "exporter"`）——`export` 流式写出（返回异步字节迭代器）。
- `NullExporter`：占位实现——空流（**不写文件**）。
- `get_exporter`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：结果文件由调用方经 02-4-1 `BaseObjectStorage` 落对象存储 / 直接回下载流；导出脱敏（敏感字段掩码）经
02-3-5 `BaseMasker` 在传入 `rows` 前完成，本契约不内置脱敏。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import cast

from fastapi import Request

from app.core.capability import BaseCapability, BaseNullObject
from app.transfer.base import ColumnSpec

__all__ = [
    "BaseExporter",
    "NullExporter",
    "get_exporter",
]


class BaseExporter(BaseCapability, ABC):
    """导出契约：按列定义流式写出。"""

    key: str = "exporter"

    @abstractmethod
    def export(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        columns: Sequence[ColumnSpec],
    ) -> AsyncIterator[bytes]:
        """按列定义流式写出（分块产出字节）。

        Args:
            rows: 数据行。
            columns: 列定义。

        Returns:
            AsyncIterator[bytes]: 字节分块异步迭代器。
        """


class _EmptyExporterStream:
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
        rows: Sequence[Mapping[str, object]],
        *,
        columns: Sequence[ColumnSpec],
    ) -> AsyncIterator[bytes]:
        """返回空异步迭代流。

        Args:
            rows: 数据行（占位忽略）。
            columns: 列定义（占位忽略）。

        Returns:
            AsyncIterator[bytes]: 空流（无分块）。
        """
        return _EmptyExporterStream()


def get_exporter(request: Request) -> BaseExporter:
    """取应用级导出器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseExporter: 应用装配的导出器实例。
    """
    return cast("BaseExporter", request.app.state.exporter)
