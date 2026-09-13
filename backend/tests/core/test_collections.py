"""有序集合基类测试（Kiwi 15）。"""

import pytest

from app.core.base import BaseObject
from app.core.collections import BaseSorted, SortedDict, SortedList, SortedSet


@pytest.mark.kiwi_id(15)
def test_inheritance_chain() -> None:
    """有序集合继承链：BaseSorted → BaseObject；Sorted* → BaseSorted。"""
    assert issubclass(BaseSorted, BaseObject)
    assert issubclass(SortedList, BaseSorted)
    assert issubclass(SortedDict, BaseSorted)
    assert issubclass(SortedSet, BaseSorted)


@pytest.mark.kiwi_id(15)
def test_insert_keeps_sorted_order() -> None:
    """插入即有序（遍历与查询顺序稳定一致）。"""
    items = SortedList([3, 1, 2])
    assert items.to_list() == [1, 2, 3]
    items.add(0)
    assert items.to_list() == [0, 1, 2, 3]
    assert SortedSet(["b", "a"]).to_list() == ["a", "b"]
    assert SortedDict({"b": 2, "a": 1}).to_list() == [("a", 1), ("b", 2)]


@pytest.mark.kiwi_id(15)
def test_stable_serialization() -> None:
    """稳定序列化：to_list/to_dict/to_json。"""
    assert SortedList([2, 1]).to_json() == "[1, 2]"
    assert SortedSet([2, 1]).to_json() == "[1, 2]"
    mapping = SortedDict({"b": 2, "a": 1})
    assert mapping.to_dict() == {"a": 1, "b": 2}
    assert list(mapping.to_dict()) == ["a", "b"]
    assert mapping.to_json() == '{"a": 1, "b": 2}'


@pytest.mark.kiwi_id(15)
def test_sequence_classes_reject_to_dict() -> None:
    """序列类调用 to_dict 抛 TypeError（指向 to_list）。"""
    with pytest.raises(TypeError):
        SortedList([1]).to_dict()
    with pytest.raises(TypeError):
        SortedSet([1]).to_dict()


@pytest.mark.kiwi_id(15)
def test_sorted_by_and_chunk() -> None:
    """排序视图与分批（含整批与尾批）。"""
    items = SortedList([3, 1, 2])
    assert items.sorted_by(lambda value: -value) == [3, 2, 1]
    assert list(items.chunk(2)) == [[1, 2], [3]]
    assert list(items.chunk(3)) == [[1, 2, 3]]
    with pytest.raises(ValueError):
        list(items.chunk(0))


@pytest.mark.kiwi_id(15)
def test_merge_keeps_order_and_type() -> None:
    """多路归并保序且返回同类（字典同键后者覆盖）。"""
    merged = SortedList([1, 3]).merge([2, 4])
    assert isinstance(merged, SortedList)
    assert merged.to_list() == [1, 2, 3, 4]
    merged_set = SortedSet([1]).merge([2, 2])
    assert merged_set.to_list() == [1, 2]
    merged_dict = SortedDict({"a": 1}).merge([("b", 2), ("a", 3)])
    assert merged_dict.to_dict() == {"a": 3, "b": 2}


@pytest.mark.kiwi_id(15)
def test_set_operations_and_dict_key_ops() -> None:
    """集合运算保序；字典按键交并。"""
    left = SortedSet([1, 2, 3])
    right = SortedSet([2, 3, 4])
    assert (left & right).to_list() == [2, 3]
    union = left | right
    assert isinstance(union, SortedSet)
    assert union.to_list() == [1, 2, 3, 4]

    mapping = SortedDict({"a": 1, "b": 2})
    assert mapping.keys_intersection(["b", "c"]).to_dict() == {"b": 2}
    assert mapping.keys_union({"b": 9, "c": 3}).to_dict() == {"a": 1, "b": 9, "c": 3}


@pytest.mark.kiwi_id(15)
def test_str_and_repr_show_content() -> None:
    """__str__/__repr__ 内容式展示。"""
    items = SortedList([1])
    assert str(items) == repr(items)
    assert "1" in str(items)
