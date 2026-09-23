"""排序与游标公共实现测试（Kiwi 1078）：ORDER BY NULL 末位、键集谓词、内存排序与索引断言。"""

from dataclasses import dataclass

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.engine import Dialect

from bms_core.core.exceptions import ConfigError
from bms_core.models.platform import SysModule
from bms_core.repositories.ordering import (
    assert_sortable_fields_indexed,
    is_after_cursor,
    keyset_condition,
    order_criteria,
    sort_items,
)
from bms_core.schemas.sorting import SortDirection, SortSpec

_PROBE = Table(
    "order_probe",
    MetaData(),
    Column("id", BigInteger, primary_key=True, autoincrement=False),
    Column("rank", Integer, nullable=True),
)
"""排序探针表（覆盖可空排序列与主键兜底）。"""


def _dialect(name: str) -> Dialect:
    """取方言实例（达梦经 `dmSQLAlchemy` 注册，不建连）。

    Args:
        name: sqlite / mysql / postgresql / dm。

    Returns:
        Dialect: 方言实例。
    """
    if name == "sqlite":
        return sqlite.dialect()
    if name == "mysql":
        return mysql.dialect()
    if name == "postgresql":
        return postgresql.dialect()
    return create_engine("dm+dmPython://user:password@localhost:5236").dialect


def _resolve(field: str) -> object:
    """探针表字段解析器（白名单内返回列，其余 None）。"""
    if field in {"id", "rank"}:
        return _PROBE.c[field]
    return None


@pytest.mark.kiwi_id(1078)
@pytest.mark.parametrize("name", ["sqlite", "mysql", "postgresql", "dm"])
def test_order_criteria_nulls_last_across_dialects(name: str) -> None:
    """四库 ORDER BY：NULL 位次用 `列 IS NULL` 排序键表达（无 `NULLS FIRST/LAST` 字面量）。"""
    sort = [
        SortSpec(field="rank", direction=SortDirection.DESC),
        SortSpec(field="ghost"),
    ]
    criteria = order_criteria(sort, resolve=_resolve, id_column=_PROBE.c.id)
    statement = select(_PROBE.c.id).order_by(*criteria)
    sql = str(statement.compile(dialect=_dialect(name), compile_kwargs={"literal_binds": True}))
    assert "IS NULL ASC" in sql
    assert "rank` DESC" in sql or "rank DESC" in sql
    assert "id ASC" in sql
    assert "NULLS LAST" not in sql.upper()
    assert "NULLS FIRST" not in sql.upper()


@pytest.mark.kiwi_id(1078)
def test_order_criteria_defaults_to_id_asc() -> None:
    """排序规格为空 / 全被忽略时回落 `id ASC`（稳定序，不产生空 ORDER BY）。"""
    criteria = order_criteria([], resolve=_resolve, id_column=_PROBE.c.id)
    sql = str(select(_PROBE.c.id).order_by(*criteria).compile(dialect=sqlite.dialect()))
    assert "ORDER BY order_probe.id ASC" in sql


@pytest.mark.kiwi_id(1078)
def test_keyset_condition_shape() -> None:
    """键集谓词：元素大于用 `IS NULL OR >`（升序）/ `IS NULL OR <`（降序）+ 主键尾键。"""
    sort = [SortSpec(field="rank", direction=SortDirection.ASC)]
    predicate = keyset_condition(
        sort,
        (("rank", "asc"),),
        (5,),
        10,
        resolve=_resolve,
        id_column=_PROBE.c.id,
    )
    sql = str(
        select(_PROBE.c.id).where(predicate).compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "rank IS NULL OR order_probe.rank > 5" in sql
    assert "order_probe.id > 10" in sql


@pytest.mark.kiwi_id(1078)
def test_keyset_condition_with_null_cursor_value() -> None:
    """游标键值为 NULL 时该位恒假（NULL 组内无更大者）→ 续查只落主键尾键。"""
    sort = [SortSpec(field="rank", direction=SortDirection.ASC)]
    predicate = keyset_condition(
        sort,
        (("rank", "asc"),),
        (None,),
        10,
        resolve=_resolve,
        id_column=_PROBE.c.id,
    )
    sql = str(
        select(_PROBE.c.id).where(predicate).compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "order_probe.rank > " not in sql
    assert "rank IS NULL" in sql
    assert "order_probe.id > 10" in sql


@pytest.mark.kiwi_id(1078)
def test_keyset_condition_rejects_unwhitelisted_field() -> None:
    """生效排序字段不在可排序列（白名单 / 映射列之外）→ `ConfigError`。"""
    with pytest.raises(ConfigError):
        keyset_condition(
            [SortSpec(field="ghost", direction=SortDirection.ASC)],
            (("ghost", "asc"),),
            (1,),
            1,
            resolve=_resolve,
            id_column=_PROBE.c.id,
        )


@dataclass
class Row:
    """内存排序测试条目（`rank` 取 `object` 以覆盖混合类型兜底分支）。"""

    id: int
    rank: object = None
    name: str = ""


@pytest.mark.kiwi_id(1078)
def test_sort_items_nulls_last_multi_key() -> None:
    """内存排序：NULL 恒末位（升 / 降一致）、多键主次生效、主键兜底稳定序。"""
    rows = [
        Row(1, 2, "b"),
        Row(2, None, "x"),
        Row(3, 1, "c"),
        Row(4, 1, "a"),
    ]
    asc = sort_items(rows, [SortSpec(field="rank", direction=SortDirection.ASC)], id_of=lambda row: row.id)
    assert [(row.rank, row.name) for row in asc] == [(1, "c"), (1, "a"), (2, "b"), (None, "x")]
    desc = sort_items(rows, [SortSpec(field="rank", direction=SortDirection.DESC)], id_of=lambda row: row.id)
    assert [(row.rank, row.name) for row in desc] == [(2, "b"), (1, "c"), (1, "a"), (None, "x")]

    multi = sort_items(
        rows,
        [
            SortSpec(field="rank", direction=SortDirection.ASC),
            SortSpec(field="name", direction=SortDirection.DESC),
        ],
        id_of=lambda row: row.id,
    )
    assert [(row.rank, row.name) for row in multi] == [(1, "c"), (1, "a"), (2, "b"), (None, "x")]


@pytest.mark.kiwi_id(1078)
def test_is_after_cursor_mirrors_sql_predicate() -> None:
    """内存键集判定与 SQL 谓词同口径：NULL 组内靠主键、非空组按方向比较。"""
    sort = [SortSpec(field="rank", direction=SortDirection.ASC)]
    # 非空游标：更大的非空值在后；NULL 行也在后
    assert is_after_cursor(Row(9, 6), sort, (5,), 9, id_of=lambda row: row.id) is True
    assert is_after_cursor(Row(9, 4), sort, (5,), 9, id_of=lambda row: row.id) is False
    assert is_after_cursor(Row(9, None), sort, (5,), 9, id_of=lambda row: row.id) is True
    # NULL 游标：非空行在前（False），NULL 行按主键续查
    assert is_after_cursor(Row(9, 4), sort, (None,), 9, id_of=lambda row: row.id) is False
    assert is_after_cursor(Row(10, None), sort, (None,), 9, id_of=lambda row: row.id) is True
    assert is_after_cursor(Row(9, None), sort, (None,), 9, id_of=lambda row: row.id) is False


@pytest.mark.kiwi_id(1078)
def test_assert_sortable_fields_indexed() -> None:
    """索引配合断言：主键 / 索引列通过；无索引字段抛 `ConfigError`；非 ORM 模型拒绝。"""
    assert_sortable_fields_indexed(SysModule, {"id", "deleted_at"})
    with pytest.raises(ConfigError):
        assert_sortable_fields_indexed(SysModule, {"name"})
    with pytest.raises(ConfigError):
        assert_sortable_fields_indexed(Row, {"rank"})


@pytest.mark.kiwi_id(1078)
def test_order_criteria_keeps_id_when_already_sorted() -> None:
    """排序规格已含主键时不重复追加 `id ASC`（多规格短路口径）。"""
    sort = [
        SortSpec(field="id", direction=SortDirection.DESC),
        SortSpec(field="rank", direction=SortDirection.ASC),
    ]
    criteria = order_criteria(sort, resolve=_resolve, id_column=_PROBE.c.id)
    sql = str(select(_PROBE.c.id).order_by(*criteria).compile(dialect=sqlite.dialect()))
    assert "order_probe.id DESC" in sql
    assert "order_probe.id ASC" not in sql


@pytest.mark.kiwi_id(1078)
def test_keyset_direction_falls_back_to_effective_spec() -> None:
    """游标指纹方向非法时回落生效规格方向（不抛错、不静默错序）。"""
    predicate = keyset_condition(
        [SortSpec(field="rank", direction=SortDirection.DESC)],
        (("rank", "sideways"),),
        (5,),
        10,
        resolve=_resolve,
        id_column=_PROBE.c.id,
    )
    sql = str(
        select(_PROBE.c.id).where(predicate).compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "order_probe.rank < 5" in sql


@pytest.mark.kiwi_id(1078)
def test_is_after_cursor_desc_and_incomparable_values() -> None:
    """降序方向比较与不可比类型兜底（视为相等 → 落到主键尾键，不抛 TypeError）。"""
    desc = [SortSpec(field="rank", direction=SortDirection.DESC)]
    assert is_after_cursor(Row(9, 4), desc, (5,), 9, id_of=lambda row: row.id) is True
    assert is_after_cursor(Row(9, 6), desc, (5,), 9, id_of=lambda row: row.id) is False
    mixed = Row(10, "字")
    assert is_after_cursor(mixed, desc, (5,), 9, id_of=lambda row: row.id) is True


@pytest.mark.kiwi_id(1078)
def test_private_sort_key_and_compare_type_buckets() -> None:
    """排序键类型分桶与不可比比较兜底（私有助手；混合类型不抛 TypeError）。"""
    from datetime import date, datetime

    from bms_core.repositories import ordering

    assert ordering._value_key(None) == ("~", "")  # pyright: ignore[reportPrivateUsage]
    assert ordering._value_key(True) == ("b", 1)  # pyright: ignore[reportPrivateUsage]
    assert ordering._value_key(1.5) == ("f", 1.5)  # pyright: ignore[reportPrivateUsage]
    assert ordering._value_key(datetime(2026, 9, 22))[0] == "t"  # pyright: ignore[reportPrivateUsage]
    assert ordering._value_key(date(2026, 9, 22))[0] == "d"  # pyright: ignore[reportPrivateUsage]
    assert ordering._value_key(object())[0] == "o"  # pyright: ignore[reportPrivateUsage]
    assert ordering._compare(1, "字") == 0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(1078)
def test_assert_sortable_fields_indexed_counts_single_column_unique() -> None:
    """单列唯一约束列视为已索引（复合唯一约束不视为单列可排序索引）。"""
    from sqlalchemy import UniqueConstraint

    probe = Table(
        "index_probe",
        MetaData(),
        Column("id", BigInteger, primary_key=True, autoincrement=False),
        Column("code", Integer),
        UniqueConstraint("code", name="uq_index_probe_code"),
    )

    class _ProbeModel:
        __table__ = probe
        __name__ = "_ProbeModel"

    assert_sortable_fields_indexed(_ProbeModel, {"id", "code"})


@pytest.mark.kiwi_id(1078)
def test_keyset_condition_handles_short_fingerprint() -> None:
    """游标指纹项少于生效排序规格时按生效规格方向续查（不越界）。"""
    sort = [
        SortSpec(field="rank", direction=SortDirection.DESC),
        SortSpec(field="id", direction=SortDirection.ASC),
    ]
    predicate = keyset_condition(
        sort,
        (("rank", "desc"),),
        (5, None),
        10,
        resolve=_resolve,
        id_column=_PROBE.c.id,
    )
    sql = str(
        select(_PROBE.c.id).where(predicate).compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "order_probe.rank < 5" in sql
