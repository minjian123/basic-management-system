"""导入导出能力域 · 导入：解析 / 行校验 / 错误回执契约（真实 openpyxl 随通用能力阶段回补）。

- `RowError` / `ImportResult`：行错误回执与导入结果数据契约（frozen）。
- `BaseImporter`：能力域中间层契约（`key = "importer"`）——异步 `parse`（解析为行）/ `validate`（行校验 → 结果 + 回执）。
- `get_importer`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：文件字节由调用方经 02-4-1 `BaseObjectStorage` 取后传入；批量入库幂等（幂等键 + 唯一约束兜底）归上层。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.transfer.base import ColumnSpec

__all__ = [
    "BaseImporter",
    "ImportResult",
    "RowError",
    "get_importer",
]


@dataclass(frozen=True)
class RowError(BaseObject):
    """行错误回执。"""

    row: int
    """行号（数据行，从 1 起）。"""

    message: str
    """错误说明。"""

    field: str | None = None
    """出错字段（可选）。"""


@dataclass(frozen=True)
class ImportResult(BaseObject):
    """导入结果：有效行 + 错误回执。"""

    rows: tuple[Mapping[str, object], ...]
    """有效行。"""

    errors: tuple[RowError, ...] = ()
    """错误回执。"""


class BaseImporter(BasePluggable, ABC):
    """导入契约：解析 / 行校验 / 错误回执。"""

    key: str = "importer"
    plugin_key: str = "importer"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def parse(self, data: bytes, *, columns: Sequence[ColumnSpec]) -> tuple[Mapping[str, object], ...]:
        """解析文件字节为行（不做业务校验）。

        Args:
            data: 文件字节。
            columns: 列定义。

        Returns:
            tuple[Mapping[str, object], ...]: 解析出的原始行。
        """

    @abstractmethod
    async def validate(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        columns: Sequence[ColumnSpec],
    ) -> ImportResult:
        """行校验：筛出有效行 + 错误回执。

        Args:
            rows: 原始行。
            columns: 列定义。

        Returns:
            ImportResult: 有效行与错误回执。
        """


def get_importer(request: Request) -> BaseImporter:
    """取应用级导入器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseImporter: 应用装配的导入器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseImporter",
        resolve_plugin(
            "importer",
            settings.importer.provider,
            expected_version=BaseImporter.contract_version,
        ),
    )
