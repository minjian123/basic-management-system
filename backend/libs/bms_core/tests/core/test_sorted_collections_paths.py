"""升序形态集合（`ConcurrentSorted*`）等同判定与集合运算边界用例。

补齐既有用例未触达的分支：升序列表与同类 / 稳定列表比较、升序集合并集多处新增、
以及三类升序集合遇非同族对象时的 `NotImplemented` 边界。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.sorted_collections import (
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
)


def test_sorted_list_equality_paths() -> None:
    """升序列表等同判定：`list` / 同类 / 稳定列表按元素比较；非同族返回 `NotImplemented`。"""
    values = ConcurrentSortedList([1, 2, 3])
    assert values == [1, 2, 3]
    assert values == ConcurrentSortedList([1, 2, 3])
    assert values == ConcurrentStableList([1, 2, 3])
    assert values.__eq__(object()) is NotImplemented


def test_sorted_set_union_loop_and_equality() -> None:
    """升序集合：并集多处新增（循环续行）与非同族等同判定。"""
    values = ConcurrentSortedSet([1])
    merged = values | {1, 2, 3}
    assert sorted(merged) == [1, 2, 3]
    assert values.__eq__(object()) is NotImplemented


def test_sorted_dict_equality_with_mapping_and_foreign() -> None:
    """升序映射：与 `dict` 按内容比较；非同族返回 `NotImplemented`。"""
    values = ConcurrentSortedDict({"a": 1})
    assert values == {"a": 1}
    assert values.__eq__(object()) is NotImplemented
