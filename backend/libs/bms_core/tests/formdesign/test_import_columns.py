"""导入模板列派生（Kiwi 2526）：布局序优先、未引用列保序追加、空布局等于原列集。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList
from bms_core.formdesign.import_columns import derive_import_columns, merge_column_specs
from bms_core.transfer.base import ColumnSpec

pytestmark = pytest.mark.kiwi_id(2526)


def _spec(key: str, title: str = "", required: bool = False) -> ColumnSpec:
    """构造列规格（标题缺省用键）。"""
    return ColumnSpec(key=key, title=title or key, required=required)


def test_derive_follows_layout_order_then_appends_rest() -> None:
    """布局字段序在前，未引用的基线列保序追加在末尾（不丢列）。"""
    layout_keys = ConcurrentStableFrozenList(("b", "a"))
    base = ConcurrentStableDict({"a": _spec("a"), "b": _spec("b"), "c": _spec("c")})
    derived = derive_import_columns(
        layout_keys=layout_keys,
        extra_specs=ConcurrentStableDict(),
        layout_specs=ConcurrentStableDict(),
        base_specs=base,
    )
    assert [spec.key for spec in derived] == ["b", "a", "c"]


def test_derive_appends_ext_fields_in_layout_position() -> None:
    """自建字段按其布局位置插入（不在末尾堆叠）。"""
    layout_keys = ConcurrentStableFrozenList(("a", "ext1", "b"))
    extra = ConcurrentStableDict({"ext1": _spec("ext1", "自建一", True)})
    base = ConcurrentStableDict({"a": _spec("a"), "b": _spec("b")})
    derived = derive_import_columns(
        layout_keys=layout_keys,
        extra_specs=extra,
        layout_specs=ConcurrentStableDict(),
        base_specs=base,
    )
    assert [spec.key for spec in derived] == ["a", "ext1", "b"]
    assert derived[1].required is True


def test_derive_skips_keys_without_any_spec() -> None:
    """布局引用但无任何规格的键跳过（不产空列）。"""
    derived = derive_import_columns(
        layout_keys=ConcurrentStableFrozenList(("ghost", "a")),
        extra_specs=ConcurrentStableDict(),
        layout_specs=ConcurrentStableDict(),
        base_specs=ConcurrentStableDict({"a": _spec("a")}),
    )
    assert [spec.key for spec in derived] == ["a"]


def test_merge_without_layout_equals_base() -> None:
    """无布局配置（空键序）时派生结果等于基线列集（既有导入行为零变化）。"""
    base = ConcurrentStableDict({"a": _spec("a"), "b": _spec("b")})
    derived = merge_column_specs(
        layout_keys=ConcurrentStableFrozenList(()),
        extra_specs=ConcurrentStableDict(),
        layout_specs=ConcurrentStableDict(),
        base_specs=base,
    )
    assert [spec.key for spec in derived] == ["a", "b"]
