"""导入导出能力域 · 导出：列定义 / 流式写出契约（真实 openpyxl 随通用能力阶段回补）。

- `BaseExporter`：能力域中间层契约（`key = "exporter"`）——`export` 流式写出（返回异步字节迭代器）。
- `get_exporter`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：结果文件由调用方经 02-4-1 `BaseObjectStorage` 落对象存储 / 直接回下载流；导出脱敏（敏感字段掩码）经
02-3-5 `BaseMasker` 在传入 `rows` 前完成，本契约不内置脱敏。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.transfer.base import ColumnSpec

__all__ = [
    "BaseExporter",
    "get_exporter",
]


class BaseExporter(BasePluggable, ABC):
    """导出契约：按列定义流式写出。"""

    key: str = "exporter"
    plugin_key: str = "exporter"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

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


def get_exporter(request: Request) -> BaseExporter:
    """取应用级导出器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseExporter: 应用装配的导出器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseExporter",
        resolve_plugin(
            "exporter",
            settings.exporter.provider,
            expected_version=BaseExporter.contract_version,
        ),
    )
