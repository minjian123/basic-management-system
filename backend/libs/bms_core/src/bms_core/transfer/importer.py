"""导入导出能力域 · 导入：解析 / 行校验 / 错误回执契约。

- `ParsedRow`：带 Excel 行号的解析行（04_01 新增；业务定义按行号报错）。
- `RowError` / `ImportResult`：行错误回执与导入结果数据契约（frozen）。
- `BaseImporter`：能力域中间层契约（`key = "importer"`）——
  `parse_rows` / `validate_rows` 为 0.2.0 新口径（带行号）；旧 `parse` / `validate` 保留委托。
- `get_importer`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：文件字节由调用方经 `BaseObjectStorage` 取后传入；批量入库幂等（幂等键 + 唯一约束兜底）归上层。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject
from bms_core.core.plugin import NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.transfer.base import COLUMN_VALUE_TYPES, ColumnSpec

__all__ = [
    "BaseImporter",
    "ImportResult",
    "ParsedRow",
    "RowError",
    "get_importer",
]

_TRUE_VALUES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("true", "1", "是", "y", "yes", "on"))
"""布尔真值文本（大小写不敏感）。"""

_FALSE_VALUES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("false", "0", "否", "n", "no", "off"))
"""布尔假值文本（大小写不敏感）。"""


@dataclass(frozen=True)
class ParsedRow(BaseValueObject):
    """解析行：Excel 物理行号 + 字段值。

    `row_no` 从 2 起（第 1 行为表头），与错误报告、前端展示一致。
    """

    row_no: int
    """Excel 行号（数据行，从 2 起）。"""

    values: ConcurrentStableFrozenDict[str, object]
    """字段键 → 原始值（已按列定义做文本清洗 / 日期转 ISO）。"""


@dataclass(frozen=True)
class RowError(BaseValueObject):
    """行错误回执。"""

    row: int
    """行号（数据行，从 1 起）。"""

    message: str
    """错误说明。"""

    field: str | None = None
    """出错字段（可选；API 层对外映射为 `column`）。"""


@dataclass(frozen=True)
class ImportResult(BaseValueObject):
    """导入结果：有效行 + 错误回执。

    `rows` 保留 0.1.0 的字段口径（字段键 → 值）；`valid_rows` 为 0.2.0 新口径（带行号）。
    业务编排统一消费 `valid_rows`。
    """

    rows: ConcurrentStableFrozenList[ConcurrentStableFrozenDict[str, object]] = field(
        default_factory=lambda: ConcurrentStableFrozenList[ConcurrentStableFrozenDict[str, object]]()
    )
    """有效行（旧口径，丢弃行号）。"""

    errors: ConcurrentStableFrozenList[RowError] = field(default_factory=lambda: ConcurrentStableFrozenList[RowError]())
    """错误回执。"""

    valid_rows: ConcurrentStableFrozenList[ParsedRow] = field(
        default_factory=lambda: ConcurrentStableFrozenList[ParsedRow]()
    )
    """有效行（新口径，带行号；与 `rows` 一一对应）。"""


class BaseImporter(BasePluggable, ABC):
    """导入契约：解析 / 行校验 / 错误回执。"""

    key: str = "importer"
    plugin_key: str = "importer"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = "0.2.0"

    @abstractmethod
    async def parse_rows(
        self, data: bytes, *, columns: ConcurrentStableList[ColumnSpec]
    ) -> ConcurrentStableList[ParsedRow]:
        """解析文件字节为带行号的原始行（不做业务校验）。

        Args:
            data: 文件字节。
            columns: 列定义。

        Returns:
            ConcurrentStableList[ParsedRow]: 解析出的原始行。
        """

    async def parse(
        self, data: bytes, *, columns: ConcurrentStableList[ColumnSpec]
    ) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
        """旧口径：解析为无行号的行字典（委托 `parse_rows`）。

        Args:
            data: 文件字节。
            columns: 列定义。

        Returns:
            ConcurrentStableList[ConcurrentStableDict[str, object]]: 解析出的行字典。
        """
        rows = await self.parse_rows(data, columns=columns)
        return ConcurrentStableList(ConcurrentStableDict[str, object](row.values) for row in rows)

    @abstractmethod
    async def validate_rows(
        self,
        rows: ConcurrentStableList[ParsedRow],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> ImportResult:
        """行校验：筛出有效行 + 错误回执（带行号）。

        Args:
            rows: 原始行。
            columns: 列定义。

        Returns:
            ImportResult: 有效行与错误回执。
        """

    async def validate(
        self,
        rows: ConcurrentStableList[ConcurrentStableDict[str, object]],
        *,
        columns: ConcurrentStableList[ColumnSpec],
    ) -> ImportResult:
        """旧口径：按 2 起顺延行号后委托 `validate_rows`。

        Args:
            rows: 原始行字典。
            columns: 列定义。

        Returns:
            ImportResult: 有效行与错误回执。
        """
        parsed = ConcurrentStableList(
            ParsedRow(row_no=index + 2, values=ConcurrentStableFrozenDict[str, object](dict(row)))
            for index, row in enumerate(rows)
        )
        return await self.validate_rows(parsed, columns=columns)

    @staticmethod
    def generic_validate_row(
        row: ParsedRow, columns: ConcurrentStableList[ColumnSpec]
    ) -> ConcurrentStableDict[str, object]:
        """通用行校验（必填 / 长度 / 类型 / 正则 / 可选值）。

        Args:
            row: 原始行。
            columns: 列定义。

        Returns:
            ConcurrentStableDict[str, object]: 字段键 → 清洗后的值（仅当无错误时有意义）。

        Raises:
            _RowInvalid: 任一列校验失败（由 `validate_rows` 捕获并转 `RowError`）。
        """
        converted: ConcurrentStableDict[str, object] = ConcurrentStableDict()
        failures: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        for column in columns:
            raw = row.values.get(column.key)
            value = _clean(raw)
            if value is None:
                if column.required:
                    failures.add((column.key, f"{column.title}必填"))
                converted.set(column.key, None)
                continue
            try:
                value = _convert_type(value, column)
            except _ColumnInvalid as exc:
                failures.add((exc.field, str(exc)))
                continue
            text = "" if value is None else str(value)
            if column.max_length is not None and len(text) > column.max_length:
                failures.add((column.key, f"{column.title}长度不能超过 {column.max_length}"))
                continue
            if column.pattern is not None and re.fullmatch(column.pattern, text) is None:
                failures.add((column.key, f"{column.title}格式非法"))
                continue
            if column.choices and text not in column.choices:
                failures.add((column.key, f"{column.title}取值非法"))
                continue
            converted.set(column.key, value)
        if failures:
            raise _RowInvalid(failures)
        return converted


class _ColumnInvalid(ParamError):
    """单列校验失败（内部异常，转 `RowError`）。"""

    def __init__(self, field: str, message: str) -> None:
        """初始化。

        Args:
            field: 字段键。
            message: 错误说明。
        """
        super().__init__(message)
        self.field = field
        self.message = message


class _RowInvalid(ParamError):
    """一行多列校验失败（内部异常，转多条 `RowError`）。"""

    def __init__(self, failures: ConcurrentStableList[tuple[str, str]]) -> None:
        """初始化。

        Args:
            failures: （字段键, 错误说明）列表。
        """
        super().__init__("行校验失败")
        self.failures = failures


def _clean(value: object) -> object | None:
    """清洗单元格值：字符串去空白，空串视为空。

    Args:
        value: 原始值。

    Returns:
        object | None: 清洗后的值；空值返回 None。
    """
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _convert_type(value: object, column: ColumnSpec) -> object:
    """按列定义转换值。

    Args:
        value: 清洗后的非空值。
        column: 列定义。

    Returns:
        object: 转换后的值。

    Raises:
        _ColumnInvalid: 类型不合法。
    """
    value_type = column.value_type or "text"
    if value_type not in COLUMN_VALUE_TYPES:
        raise _ColumnInvalid(column.key, f"{column.title}列类型配置非法")
    if value_type == "text":
        if isinstance(value, datetime):
            return value.isoformat(sep=" ")
        if isinstance(value, date):
            return value.isoformat()
        return str(value)
    if value_type == "int":
        if isinstance(value, bool):
            raise _ColumnInvalid(column.key, f"{column.title}必须为整数")
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise _ColumnInvalid(column.key, f"{column.title}必须为整数") from exc
        return parsed
    if value_type == "number":
        if isinstance(value, bool):
            raise _ColumnInvalid(column.key, f"{column.title}必须为数字")
        try:
            return float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise _ColumnInvalid(column.key, f"{column.title}必须为数字") from exc
    if value_type == "bool":
        text = str(value).strip().lower()
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
        raise _ColumnInvalid(column.key, f"{column.title}必须为布尔值")
    if value_type == "date":
        return _parse_datetime(value, column, date_only=True)
    return _parse_datetime(value, column, date_only=False)


def _parse_datetime(value: object, column: ColumnSpec, *, date_only: bool) -> object:
    """解析日期 / 日期时间（Excel 日期或 ISO 文本）。

    Args:
        value: 原始值。
        column: 列定义。
        date_only: 是否只保留日期。

    Returns:
        object: `date` 或 `datetime`。

    Raises:
        _ColumnInvalid: 格式非法。
    """
    if isinstance(value, datetime):
        return value.date() if date_only else value
    if isinstance(value, date):
        return value if date_only else datetime.combine(value, datetime.min.time())
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _ColumnInvalid(column.key, f"{column.title}日期格式非法") from exc
    return parsed.date() if date_only else parsed


async def validate_rows_common(
    rows: ConcurrentStableList[ParsedRow],
    *,
    columns: ConcurrentStableList[ColumnSpec],
) -> ImportResult:
    """通用行校验实现（供真实导入器与占位实现复用）。

    Args:
        rows: 原始行。
        columns: 列定义。

    Returns:
        ImportResult: 有效行（新旧两套口径）与错误回执。
    """
    valid: ConcurrentStableList[ParsedRow] = ConcurrentStableList()
    dict_rows: ConcurrentStableList[ConcurrentStableFrozenDict[str, object]] = ConcurrentStableList()
    errors: ConcurrentStableList[RowError] = ConcurrentStableList()
    for row in rows:
        try:
            converted = BaseImporter.generic_validate_row(row, columns)
        except _RowInvalid as exc:
            for field, message in exc.failures:
                errors.add(RowError(row=row.row_no, message=message, field=field))
            continue
        parsed = ParsedRow(row_no=row.row_no, values=ConcurrentStableFrozenDict[str, object](converted))
        valid.add(parsed)
        dict_rows.add(parsed.values)
    return ImportResult(
        rows=ConcurrentStableFrozenList(dict_rows),
        errors=ConcurrentStableFrozenList(errors),
        valid_rows=ConcurrentStableFrozenList(valid),
    )


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
