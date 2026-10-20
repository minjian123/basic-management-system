"""字典可直用 / 可继承实现类（02_10）：读标准字典系统字段的通用字典表数据源。

口径（需求 02-57 第 3 条）：`BaseDictDataSource`（`bms_core/datasource/base.py`）+ **可直用 / 可继承
实现类**——读标准字典系统字段 `code` / `name` / `parent_id` / `sort` / `status`，各项目**直接使用或继承**，
避免各项目重复实现取数 / 缓存 / 翻译 / 版本比对（缓存 / 翻译 / 版本比对由统一出口承载）。

- `DictTableDataSource`：**配置「数据出口标识 + 物理表」即可直接使用**（按启用 + 未软删过滤、
  按 `sort` / `id` 排序、标准列映射为通用条目）；**继承覆写 `mapping()` / `row_to_item()`** 即可定制
  （列名映射 / 本地化 / 过滤）。
- 为 **mdm 需求域二 `02_01`（参考数据域实现与字典出口）前置**。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy import Table, select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.datasource.base import BaseDictDataSource, DataSourceItem
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope

__all__ = ["DictColumnMapping", "DictTableDataSource"]


@dataclass(frozen=True)
class DictColumnMapping(BaseValueObject):
    """标准字典系统字段 → 物理列名映射（缺省即标准列名）。

    Attributes:
        value: 条目值列（字典标识，缺省 `code`）。
        label: 条目标签列（展示名称，缺省 `name`）。
        code: 条目编码列（缺省 `code`）。
        parent_id: 上级条目 ID 列（缺省 `parent_id`）。
        sort: 排序列（缺省 `sort`）。
        status: 状态列（缺省 `status`）。
        soft_delete: 软删除列（缺省 `deleted_at`）。
    """

    value: str = "code"
    label: str = "name"
    code: str = "code"
    parent_id: str = "parent_id"
    sort: str = "sort"
    status: str = "status"
    soft_delete: str = "deleted_at"


class DictTableDataSource(BaseDictDataSource):
    """可直用的字典表数据源：读标准字典系统字段（启用 + 未软删、按排序取行）。

    配置「出口标识 + 物理表」即可直接使用；继承覆写 `mapping()` / `row_to_item()` 定制列名映射与
    条目映射（本地化 / 过滤）。
    """

    def __init__(
        self,
        *,
        engines: EngineRegistry,
        data_source: str,
        table: Table,
        mapping: DictColumnMapping | None = None,
    ) -> None:
        """初始化。

        Args:
            engines: 多租户引擎注册表。
            data_source: 数据出口标识（与登记项 `DataSourceRecord.data_source` 对齐）。
            table: 字典物理表（SQLAlchemy `Table`，取标准字典系统字段）。
            mapping: 列名映射（缺省标准列名）。
        """
        self._engines = engines
        self._data_source = data_source
        self._table = table
        self._mapping = mapping or DictColumnMapping()

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 数据出口标识。
        """
        return self._data_source

    def mapping(self) -> DictColumnMapping:
        """列名映射（可继承覆写）。

        Returns:
            DictColumnMapping: 标准字段 → 物理列名。
        """
        return self._mapping

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """加载某字典的全部启用行（标准列映射为通用条目）。

        Args:
            data_source_key: 数据源标识（本实现按构造时的表取数；非本表已登记标识返回空）。
            locale: 语言（标准字典表暂不分语言；`_i18n` 附表随各域实现）。

        Returns:
            tuple[DataSourceItem, ...]: 启用行（缺关键列时返回空元组）。
        """
        mapping = self.mapping()
        columns = self._table.c
        value_col = columns.get(mapping.value)
        if value_col is None:
            return ConcurrentStableList(())
        label_col = columns.get(mapping.label)
        if label_col is None:
            label_col = value_col
        code_col = columns.get(mapping.code)
        if code_col is None:
            code_col = value_col
        parent_col = columns.get(mapping.parent_id)
        sort_col = columns.get(mapping.sort)
        status_col = columns.get(mapping.status)
        soft_delete_col = columns.get(mapping.soft_delete)
        id_col = columns.get("id")

        selected = [value_col.label("value"), label_col.label("label"), code_col.label("code")]
        if parent_col is not None:
            selected.append(parent_col.label("parent_id"))
        if sort_col is not None:
            selected.append(sort_col.label("sort"))
        if status_col is not None:
            selected.append(status_col.label("status"))
        if id_col is not None:
            selected.append(id_col.label("id"))
        statement = select(*selected)
        if status_col is not None:
            statement = statement.where(status_col == "enabled")
        if soft_delete_col is not None:
            statement = statement.where(soft_delete_col.is_(None))
        order_columns = [column for column in (sort_col, id_col) if column is not None]
        if order_columns:
            statement = statement.order_by(*order_columns)

        async with self._session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return ConcurrentStableList(
            self.row_to_item(ConcurrentStableDict({str(key): value for key, value in row.items()})) for row in rows
        )

    def row_to_item(self, row: ConcurrentStableDict[str, object]) -> DataSourceItem:
        """结果行 → 通用条目（可继承覆写定制映射 / 本地化）。

        Args:
            row: 结果行（标准列名 → 值）。

        Returns:
            DataSourceItem: 通用数据条目。
        """
        return DataSourceItem(
            id=_as_int(row.get("id")),
            value="" if row.get("value") is None else str(row.get("value")),
            label="" if row.get("label") is None else str(row.get("label")),
            code="" if row.get("code") is None else str(row.get("code")),
            parent_id=_as_optional_int(row.get("parent_id")),
            sort=_as_int(row.get("sort")),
            status="enabled" if row.get("status") is None else str(row.get("status")),
            color=None,
        )

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[DbSession]:
        """租户库会话（按当前租户上下文取引擎）。

        Yields:
            DbSession: 租户库会话。
        """
        async with session_scope(self._engines) as session:
            yield session


def _as_int(value: object) -> int:
    """宽松取整数（非法回落 0）。

    Args:
        value: 原始值。

    Returns:
        int: 整数。
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.lstrip("-").isdigit():
        return int(value)
    return 0


def _as_optional_int(value: object) -> int | None:
    """宽松取可空整数（None / 非正回落 None）。

    Args:
        value: 原始值。

    Returns:
        int | None: 整数；None / 非正为空。
    """
    if value is None:
        return None
    parsed = _as_int(value)
    return parsed if parsed > 0 else None
