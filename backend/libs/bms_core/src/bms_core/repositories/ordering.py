"""排序与游标的公共实现：ORDER BY 表达式、键集谓词、内存排序与索引配合断言。

- **NULLS 口径统一为「NULL 恒排末位」**：跨方言用 `列 IS NULL` 排序键表达——SQLAlchemy 的
  `nulls_last()` 对 MySQL 会直接渲染 `NULLS LAST`（MySQL 语法不支持），故不采用；
- **稳定序**：排序键 = 白名单字段（经模型列解析）+ 主键兜底 `id ASC`；
- **一处口径两处落地**：DB 侧 `order_criteria` / `keyset_condition` 与内存侧
  `sort_items` / `is_after_cursor` 逐条镜像，保证内存基线与数据库实现行为一致。
"""

from collections.abc import Callable, Collection, Sequence
from datetime import date, datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, Table, UniqueConstraint, and_, false, or_

from bms_core.core.exceptions import ConfigError
from bms_core.schemas.sorting import SortDirection, SortSpec

_Col = Any
"""模型列（ORM `InstrumentedAttribute` 或 Core `Column`；需支持比较与 `asc` / `desc`）。"""
_Resolver = Callable[[str], Any]
"""字段名 → 模型列解析器（返回 None 表示白名单外 / 非映射列）。"""


def order_criteria(sort: Sequence[SortSpec], *, resolve: _Resolver, id_column: _Col) -> list[ColumnElement[Any]]:
    """构造 ORDER BY 元素（NULL 恒末位 + 主键兜底）。

    Args:
        sort: 生效排序规格（白名单已过滤）。
        resolve: 字段名 → 模型列解析器。
        id_column: 主键列（稳定序兜底）。

    Returns:
        list[ColumnElement[Any]]: ORDER BY 元素列表。
    """
    criteria: list[ColumnElement[Any]] = []
    uses_id = False
    for spec in sort:
        column = resolve(spec.field)
        if column is None:
            continue
        criteria.append(cast("ColumnElement[Any]", column.is_(None).asc()))
        criteria.append(
            cast("ColumnElement[Any]", column.asc() if spec.direction is SortDirection.ASC else column.desc())
        )
        uses_id = uses_id or column.key == id_column.key
    if not uses_id:
        criteria.append(cast("ColumnElement[Any]", id_column.asc()))
    return criteria


def keyset_condition(
    sort: Sequence[SortSpec],
    payload_specs: Sequence[tuple[str, str]],
    values: Sequence[object],
    item_id: int,
    *,
    resolve: _Resolver,
    id_column: _Col,
) -> ColumnElement[bool]:
    """构造 keyset 续查谓词（严格位于游标末行之后）。

    谓词 = `ORⱼ( 前缀相等(1..j-1) AND 元素大于(j) ) OR ( 全部相等 AND id > 末行 id )`。

    Args:
        sort: 生效排序规格（与游标指纹一致）。
        payload_specs: 游标指纹（`(字段, 方向)` 序列；用于逐位取方向）。
        values: 游标末行排序键值。
        item_id: 游标末行主键。
        resolve: 字段名 → 模型列解析器。
        id_column: 主键列。

    Returns:
        ColumnElement[bool]: 续查条件。

    Raises:
        ConfigError: 生效排序字段不在白名单 / 非映射列（声明与游标不一致）。
    """
    clauses: list[ColumnElement[bool]] = []
    prefix: list[ColumnElement[bool]] = []
    for index, spec in enumerate(sort):
        column = resolve(spec.field)
        if column is None:
            raise ConfigError(f"游标续查字段不在可排序列：{spec.field}")
        direction = _direction_of(payload_specs, index, spec)
        value = values[index]
        clause = _greater_than(column, direction, value)
        clauses.append(and_(*prefix, clause) if prefix else clause)
        prefix.append(_equal(column, value))
    clauses.append(and_(*prefix, id_column > item_id))
    return or_(*clauses)


def sort_items[ItemT](
    items: Sequence[ItemT],
    sort: Sequence[SortSpec],
    *,
    id_of: Callable[[ItemT], int],
) -> list[ItemT]:
    """内存排序（NULL 恒末位 + 多键稳定序 + 主键兜底）。

    实现：先按主键（最次键）排序，再按规格逆序逐次稳定排序——每条规格先按值排序
    （方向），再把空值整体稳定移到末尾。

    Args:
        items: 待排序条目（已按默认顺序排列）。
        sort: 生效排序规格；空表示仅按主键升序。
        id_of: 取条目主键。

    Returns:
        list[ItemT]: 排序后的条目列表。
    """
    result = list(items)
    result.sort(key=id_of)
    for spec in reversed(sort):
        result.sort(
            key=lambda item, field=spec.field: _value_key(getattr(item, field, None)),  # type: ignore[arg-type]
            reverse=spec.direction is SortDirection.DESC,
        )
        result.sort(key=lambda item, field=spec.field: getattr(item, field, None) is None)
    return result


def is_after_cursor[ItemT](
    item: ItemT,
    sort: Sequence[SortSpec],
    values: Sequence[object],
    item_id: int,
    *,
    id_of: Callable[[ItemT], int],
) -> bool:
    """判断条目是否严格位于游标行之后（与 SQL 键集谓词同口径）。

    Args:
        item: 待判断条目。
        sort: 生效排序规格。
        values: 游标末行排序键值。
        item_id: 游标末行主键。
        id_of: 取条目主键。

    Returns:
        bool: 严格在后 True。
    """
    for index, spec in enumerate(sort):
        current = getattr(item, spec.field, None)
        cursor_value = values[index]
        if current is None and cursor_value is None:
            continue
        if current is None:
            return True
        if cursor_value is None:
            return False
        comparison = _compare(current, cursor_value)
        if comparison == 0:
            continue
        if spec.direction is SortDirection.ASC:
            return comparison > 0
        return comparison < 0
    return id_of(item) > item_id


def assert_sortable_fields_indexed(model: type[Any], sortable_fields: Collection[str]) -> None:
    """校验「可排序字段须有索引或为主键」（模块声明白名单时调用）。

    索引口径：主键列 + 表级索引列 + 单列唯一约束列（复合唯一约束不视为单列可排序索引）。

    Args:
        model: ORM 模型类（含 `__table__`）。
        sortable_fields: 可排序字段白名单。

    Raises:
        ConfigError: 模型无表对象，或存在缺索引的可排序字段。
    """
    table = getattr(model, "__table__", None)
    if table is None:
        raise ConfigError(f"{getattr(model, '__name__', model)} 无 __table__（仅 ORM 模型适用索引断言）")
    indexed: set[str] = {column.name for column in cast("Table", table).primary_key.columns}
    for index in cast("Table", table).indexes:
        indexed.update(column.name for column in index.columns)
    for constraint in cast("Table", table).constraints:
        if isinstance(constraint, UniqueConstraint) and len(constraint.columns) == 1:
            indexed.update(column.name for column in constraint.columns)
    missing = sorted(field for field in sortable_fields if field not in indexed)
    if missing:
        raise ConfigError(f"{model.__name__} 可排序字段缺索引：{', '.join(missing)}（建索引或移出可排序白名单）")


def _direction_of(specs: Sequence[tuple[str, str]], index: int, spec: SortSpec) -> SortDirection:
    """取游标指纹中该位的方向（缺失 / 非法回落生效规格方向）。

    Args:
        specs: 游标指纹。
        index: 位置。
        spec: 生效排序规格。

    Returns:
        SortDirection: 方向。
    """
    if index < len(specs):
        raw = specs[index][1]
        if raw == SortDirection.ASC.value:
            return SortDirection.ASC
        if raw == SortDirection.DESC.value:
            return SortDirection.DESC
    return spec.direction


def _equal(column: _Col, value: object) -> ColumnElement[bool]:
    """元素相等条件（NULL 与 NULL 视为相等）。

    Args:
        column: 模型列。
        value: 游标键值。

    Returns:
        ColumnElement[bool]: 相等条件。
    """
    if value is None:
        return cast("ColumnElement[bool]", column.is_(None))
    return column == value


def _greater_than(column: _Col, direction: SortDirection, value: object) -> ColumnElement[bool]:
    """元素严格大于条件（NULL 组在末位 → 游标为空时该位无更大者）。

    Args:
        column: 模型列。
        direction: 排序方向。
        value: 游标键值。

    Returns:
        ColumnElement[bool]: 大于条件。
    """
    if value is None:
        return cast("ColumnElement[bool]", false())
    if direction is SortDirection.ASC:
        return or_(column.is_(None), column > value)
    return or_(column.is_(None), column < value)


def _compare(current: object, cursor_value: object) -> int:
    """内存比较（类型不可比时视为相等，避免测试替身抛 TypeError）。

    Args:
        current: 当前条目值。
        cursor_value: 游标值。

    Returns:
        int: 负数（当前在前）/ 0（相等或不可比）/ 正数（当前在后）。
    """
    try:
        if current < cursor_value:  # pyright: ignore[reportOperatorIssue]
            return -1
        if current > cursor_value:  # pyright: ignore[reportOperatorIssue]
            return 1
    except TypeError:
        return 0
    return 0


def _value_key(value: object) -> tuple[str, object]:
    """内存排序键（类型分桶 + 值，保证混合类型不抛 TypeError；空值单独处理）。

    Args:
        value: 字段值。

    Returns:
        tuple[str, object]: 可比较的排序键。
    """
    if value is None:
        return ("~", "")
    if isinstance(value, bool):
        return ("b", int(value))
    if isinstance(value, int):
        return ("i", value)
    if isinstance(value, float):
        return ("f", value)
    if isinstance(value, str):
        return ("s", value)
    if isinstance(value, datetime):
        return ("t", value)
    if isinstance(value, date):
        return ("d", value)
    return ("o", str(value))
