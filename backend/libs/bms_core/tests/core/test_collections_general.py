"""集合类通用功能面测试（Kiwi 2322）：写糖 / 通用方法 / 输出可读性 / 冻结快照。

覆盖需求 08-4（08_04 集合类通用功能补齐）：

- 输出可读性：`__str__` / `__repr__` 为「类名 + 内置字面量」，超 10 项截断；跨副本描述式 repr 不抛错；
- 列表：`append` / `extend` / `+=` / `+` / `pop(i)` / `l[i] = v` / `del l[i]` / `sorted` / `merge` / `copy`；
- 字典：`d[k] = v` / `del d[k]` / `clear` / `pop` / `popitem` / `setdefault` / `fromkeys` /
  `update(映射 | 键值对 | kwargs)` / `|` / `|=` / `sorted_items` / `sorted_keys`；
- 集合：`remove` / `pop` / `copy` / 四个命名运算及 `*_update`；
- `freeze()` 冻结副本：一切写操作抛 `TypeError`；
- 升序形态 `ConcurrentSorted*` 与插入序形态同一套写法（两形态 API 不分叉）；
- 并发：多线程写糖混写不破坏插入序与线程安全。
"""

import threading
from typing import Any, cast

import pytest

from bms_core.core.collections import REPR_ITEM_LIMIT, BaseCollection, BaseSorted, render_payload
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.locking import LockStrategy
from bms_core.core.redis_collections import BaseCacheSnapshot, RedisSnapshot, RedisSortedDict, RedisSortedSet
from bms_core.core.sorted_collections import (
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
)

ALL_STRATEGIES = [LockStrategy.SHARDED, LockStrategy.RW, LockStrategy.RLCK, LockStrategy.SNAPSHOT]


# ---------------- 输出可读性 ----------------


@pytest.mark.kiwi_id(2322)
def test_render_payload_renders_builtin_literals() -> None:
    """载荷渲染：序列为 `[..]`、映射为 `{..}`，超限截断并提示总项数，非容器原样 repr。"""
    assert render_payload([1, 2]) == "[1, 2]"
    assert render_payload({"a": 1}) == "{'a': 1}"
    assert render_payload("plain") == "'plain'"

    numbers = list(range(REPR_ITEM_LIMIT + 5))
    rendered_list = render_payload(numbers)
    assert f"共 {len(numbers)} 项" in rendered_list
    assert rendered_list.startswith("[0, 1,")

    mapping = {f"k{index}": index for index in range(REPR_ITEM_LIMIT + 5)}
    rendered_dict = render_payload(mapping)
    assert f"共 {len(mapping)} 项" in rendered_dict
    assert rendered_dict.startswith("{'k0': 0,")


@pytest.mark.kiwi_id(2322)
def test_str_and_repr_use_builtin_literal_form() -> None:
    """三类形态的 `str` / `repr` 都是「类名 + 内置字面量」，且 `str` 与 `repr` 一致。"""
    items = ConcurrentStableList([1, 2])
    members = ConcurrentStableSet([3, 1])
    mapping = ConcurrentStableDict({"b": 2, "a": 1})

    assert str(items) == repr(items) == "ConcurrentStableList([1, 2])"
    assert str(members) == "ConcurrentStableSet([3, 1])"
    assert str(mapping) == "ConcurrentStableDict({'b': 2, 'a': 1})"
    # 映射不再被渲染成键值对列表（08-4 修复点）
    assert "[('b', 2)" not in repr(mapping)


@pytest.mark.kiwi_id(2322)
def test_str_truncates_long_collections() -> None:
    """超长集合截断展示（默认上限 10 项），并提示总项数。"""
    items = ConcurrentStableList(range(REPR_ITEM_LIMIT + 3))
    rendered = repr(items)
    assert f"共 {REPR_ITEM_LIMIT + 3} 项" in rendered
    assert "…" in rendered


@pytest.mark.kiwi_id(2322)
def test_async_collections_repr_never_raises() -> None:
    """跨副本形态 `repr` 为描述式（含键名），**恒不抛错**（08-4 修复点）。"""
    members: RedisSortedSet[str] = RedisSortedSet(None, "bms:global:demo:set")  # type: ignore[arg-type]
    mapping: RedisSortedDict[str, int] = cast("RedisSortedDict[str, int]", RedisSortedDict.__new__(RedisSortedDict))
    cast("Any", mapping)._key = "bms:global:demo:dict"

    assert repr(members) == "RedisSortedSet(key='bms:global:demo:set')"
    assert repr(mapping) == "RedisSortedDict(key='bms:global:demo:dict')"
    # 同步读入口仍不支持（只改了 repr，不放宽契约）
    with pytest.raises(NotImplementedError):
        members.to_list()


@pytest.mark.kiwi_id(2322)
def test_collection_root_fallback_repr_never_raises() -> None:
    """根兜底 `repr`：形态标记展示、冻结态带标记，且不触发同步读（跨副本安全）。"""
    snapshot: RedisSnapshot[object] = RedisSnapshot(None, "bms:global:demo:v", lambda: None)  # type: ignore[arg-type]
    assert repr(snapshot) == "RedisSnapshot(<cache_snapshot>)"

    frozen = ConcurrentStableList([1]).freeze()
    assert "冻结" in repr(frozen)
    assert issubclass(BaseCacheSnapshot, BaseCollection)


# ---------------- 列表通用功能 ----------------


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_list_write_sugar_equivalent_to_atomic_methods(strategy: LockStrategy) -> None:
    """列表写糖与原子方法行为等价：`append` ≡ `add`、`extend` ≡ `update`、`+=` ≡ `update`。"""
    via_sugar = ConcurrentStableList([1], strategy=strategy)
    via_sugar.append(2)
    via_sugar.extend([3, 4])
    via_sugar += [5]

    via_atomic = ConcurrentStableList([1], strategy=strategy)
    via_atomic.add(2)
    via_atomic.update([3, 4])
    via_atomic.update([5])

    assert via_sugar.to_list() == via_atomic.to_list() == [1, 2, 3, 4, 5]


@pytest.mark.kiwi_id(2322)
def test_list_add_operator_returns_new_instance() -> None:
    """`+` 返回同类新实例（原实例不变、策略保真），`copy` 亦保策略。"""
    original = ConcurrentStableList([1, 2], strategy=LockStrategy.SNAPSHOT)
    combined = original.__add__([3])  # 显式调用以避开 RUF005（`+` 语义在下方断言）
    assert combined.to_list() == [1, 2, 3]
    assert original.to_list() == [1, 2]
    assert isinstance(combined, ConcurrentStableList)
    assert cast("Any", combined)._strategy is LockStrategy.SNAPSHOT
    assert cast("Any", original.copy())._strategy is LockStrategy.SNAPSHOT


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_list_index_write_and_delete(strategy: LockStrategy) -> None:
    """按索引写删：替换保留原插入位置、删除只移除目标、负索引可用。"""
    items = ConcurrentStableList(["a", "b", "c"], strategy=strategy)
    items[1] = "B"
    assert items.to_list() == ["a", "B", "c"]
    items[-1] = "C"
    assert items.to_list() == ["a", "B", "C"]
    del items[0]
    assert items.to_list() == ["B", "C"]
    del items[-1]
    assert items.to_list() == ["B"]


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_list_pop_by_index(strategy: LockStrategy) -> None:
    """`pop(index)` 取走并删除；默认末位；越界与空表抛 `IndexError`。"""
    items = ConcurrentStableList([1, 2, 3], strategy=strategy)
    assert items.pop() == 3
    assert items.pop(0) == 1
    assert items.to_list() == [2]
    with pytest.raises(IndexError):
        items.pop(5)
    items.clear()
    with pytest.raises(IndexError):
        items.pop()


@pytest.mark.kiwi_id(2322)
def test_list_rejects_slice_assignment_and_deletion() -> None:
    """切片赋值 / 切片删除不支持（须全表重编号），消息指向「重建集合」。"""
    items = ConcurrentStableList([1, 2, 3])
    with pytest.raises(TypeError, match="重建集合"):
        items[cast("Any", slice(1, 2))] = 9
    with pytest.raises(TypeError, match="重建集合"):
        del items[cast("Any", slice(1, 2))]
    # 切片读取仍返回同类快照
    sliced = items[1:3]
    assert isinstance(sliced, ConcurrentStableList)
    assert sliced.to_list() == [2, 3]


@pytest.mark.kiwi_id(2322)
def test_list_sorted_returns_new_instance() -> None:
    """`sorted(key, reverse)` 返回同类新实例，原实例插入序不变。"""
    items = ConcurrentStableList([3, 1, 2])
    ascending = items.sorted()
    descending = items.sorted(reverse=True)
    by_abs = ConcurrentStableList([-3, 1, 2]).sorted(key=abs)
    assert ascending.to_list() == [1, 2, 3]
    assert descending.to_list() == [3, 2, 1]
    assert by_abs.to_list() == [1, 2, -3]
    assert items.to_list() == [3, 1, 2]


@pytest.mark.kiwi_id(2322)
def test_list_merge_concatenates_in_insertion_order() -> None:
    """`merge` 为顺序拼接（插入序不比较元素，故不做归并），返回同类新实例。"""
    merged = ConcurrentStableList([3, 1]).merge([2], [5])
    assert merged.to_list() == [3, 1, 2, 5]
    assert isinstance(merged, ConcurrentStableList)


# ---------------- 字典通用功能 ----------------


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_item_write_and_delete(strategy: LockStrategy) -> None:
    """`d[k] = v` ≡ `set`（已存在键保持原位置）、`del d[k]` ≡ `delete`。"""
    data = ConcurrentStableDict[str, int]({"a": 1, "b": 2}, strategy=strategy)
    data["c"] = 3
    data["a"] = 10
    assert data.to_list() == [("a", 10), ("b", 2), ("c", 3)]
    del data["b"]
    assert data.to_dict() == {"a": 10, "c": 3}
    with pytest.raises(KeyError):
        del data["zzz"]


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_update_accepts_mapping_pairs_and_kwargs(strategy: LockStrategy) -> None:
    """`update` 接受映射 / 键值对可迭代 / 关键字参数（三者可叠加，映射分支不再抛 ValueError）。"""
    data = ConcurrentStableDict[str, int]({}, strategy=strategy)
    data.update({"a": 1})
    data.update([("b", 2)])
    data.update(c=3)
    assert data.to_dict() == {"a": 1, "b": 2, "c": 3}

    combined = ConcurrentStableDict[str, int]({}, strategy=strategy)
    combined.update({"a": 1}, b=2)
    assert combined.to_dict() == {"a": 1, "b": 2}

    # 无参调用不报错（等价于空操作）
    combined.update()
    assert combined.to_dict() == {"a": 1, "b": 2}


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_pop_distinguishes_missing_from_none_value(strategy: LockStrategy) -> None:
    """`pop` 用哨兵区分「缺失」与「值为 None」：缺失且有默认返回默认，无默认抛 KeyError。"""
    data = ConcurrentStableDict[str, int | None]({"a": None, "b": 2}, strategy=strategy)
    assert data.pop("a") is None
    assert data.pop("zzz", "fallback") == "fallback"
    assert data.pop("b") == 2
    with pytest.raises(KeyError):
        data.pop("zzz")


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_popitem_is_lifo(strategy: LockStrategy) -> None:
    """`popitem` 取走最后插入的键值对（与内置 dict 一致）；空表抛 KeyError。"""
    data = ConcurrentStableDict[str, int]({"a": 1, "b": 2, "c": 3}, strategy=strategy)
    assert data.popitem() == ("c", 3)
    assert data.popitem() == ("b", 2)
    assert data.to_dict() == {"a": 1}
    data.clear()
    with pytest.raises(KeyError):
        data.popitem()


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_setdefault_and_fromkeys(strategy: LockStrategy) -> None:
    """`setdefault` 存在返回既有值（含既有值为 None）、缺失原子写入；`fromkeys` 构造同类。"""
    data = ConcurrentStableDict[str, int | None]({"a": None, "b": 2}, strategy=strategy)
    assert data.setdefault("a", 99) is None
    assert data.setdefault("b", 99) == 2
    assert data.setdefault("c", 3) == 3
    assert data.to_dict() == {"a": None, "b": 2, "c": 3}

    built: ConcurrentStableDict[str, int | None] = ConcurrentStableDict[str, int | None].fromkeys(["x", "y"], 0)
    assert isinstance(built, ConcurrentStableDict)
    assert built.to_dict() == {"x": 0, "y": 0}
    assert ConcurrentStableDict[str, int | None].fromkeys(["z"]).to_dict() == {"z": None}


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_clear_and_copy(strategy: LockStrategy) -> None:
    """`clear` 清空；`copy` 为独立副本（后续写入互不影响，策略保真）。"""
    data = ConcurrentStableDict[str, int]({"a": 1}, strategy=strategy)
    clone = data.copy()
    clone.set("b", 2)
    assert data.to_dict() == {"a": 1}
    assert clone.to_dict() == {"a": 1, "b": 2}
    assert cast("Any", clone)._strategy is strategy
    data.clear()
    assert data.to_dict() == {}


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_dict_merge_operators(strategy: LockStrategy) -> None:
    """`|` 返回同类新实例（other 覆盖、原位置不变）、`|=` 原地合并返回自身。"""
    data = ConcurrentStableDict[str, int]({"a": 1, "b": 2}, strategy=strategy)
    merged = data | {"b": 20, "c": 3}
    assert merged.to_list() == [("a", 1), ("b", 20), ("c", 3)]
    assert data.to_dict() == {"a": 1, "b": 2}
    assert isinstance(merged, ConcurrentStableDict)

    data |= {"d": 4}
    assert data.to_dict() == {"a": 1, "b": 2, "d": 4}


@pytest.mark.kiwi_id(2322)
def test_dict_sorted_helpers_return_builtin_lists() -> None:
    """`sorted_items` / `sorted_keys` 返回内置 list（排序输出，非新集合形态）。"""
    data = ConcurrentStableDict({"b": 2, "a": 1, "c": 3})
    assert data.sorted_items() == [("a", 1), ("b", 2), ("c", 3)]
    assert data.sorted_items(reverse=True) == [("c", 3), ("b", 2), ("a", 1)]
    assert data.sorted_items(key=lambda item: item[1], reverse=True) == [("c", 3), ("b", 2), ("a", 1)]
    assert data.sorted_keys() == ["a", "b", "c"]
    assert data.sorted_keys(reverse=True) == ["c", "b", "a"]
    assert type(data.sorted_items()) is list
    assert type(data.sorted_keys()) is list


# ---------------- 集合通用功能 ----------------


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_set_remove_and_pop(strategy: LockStrategy) -> None:
    """`remove` 缺失抛 KeyError；`pop` 取走首个插入元素、空集抛 KeyError。"""
    members = ConcurrentStableSet([3, 1, 2], strategy=strategy)
    members.remove(1)
    assert members.to_list() == [3, 2]
    with pytest.raises(KeyError):
        members.remove(99)

    assert members.pop() == 3
    assert members.pop() == 2
    with pytest.raises(KeyError):
        members.pop()


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_set_named_operations(strategy: LockStrategy) -> None:
    """四个命名集合运算返回同类且保插入序；`copy` 为独立副本。"""
    left = ConcurrentStableSet([1, 2, 3], strategy=strategy)
    assert left.union([3, 4]).to_list() == [1, 2, 3, 4]
    assert left.union([4], [5]).to_list() == [1, 2, 3, 4, 5]
    assert left.intersection([2, 3, 9]).to_list() == [2, 3]
    assert left.intersection([2, 3], [3, 4]).to_list() == [3]
    assert left.difference([2]).to_list() == [1, 3]
    assert left.difference([1], [3]).to_list() == [2]
    assert left.symmetric_difference([3, 4]).to_list() == [1, 2, 4]
    assert isinstance(left.union([9]), ConcurrentStableSet)

    clone = left.copy()
    clone.add(99)
    assert 99 not in left


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", ALL_STRATEGIES)
def test_set_named_update_operations(strategy: LockStrategy) -> None:
    """四个 `*_update` 原地生效并保插入序。"""
    members = ConcurrentStableSet([1, 2, 3], strategy=strategy)
    members.update([3, 4])
    assert members.to_list() == [1, 2, 3, 4]
    members.intersection_update([2, 4, 9])
    assert members.to_list() == [2, 4]
    members.difference_update([4])
    assert members.to_list() == [2]
    members.symmetric_difference_update([2, 5])
    assert members.to_list() == [5]


# ---------------- 冻结快照 ----------------


@pytest.mark.kiwi_id(2322)
def test_freeze_makes_snapshot_read_only() -> None:
    """`freeze()` 返回独立冻结副本：一切写操作抛 TypeError，读操作照常。"""
    original = ConcurrentStableList([1, 2])
    frozen = original.freeze()
    original.append(3)
    assert frozen.to_list() == [1, 2]  # 内容独立
    for mutate in (
        lambda: frozen.append(9),
        lambda: frozen.extend([9]),
        lambda: frozen.__setitem__(0, 9),
        lambda: frozen.__delitem__(0),
        lambda: frozen.pop(),
        lambda: frozen.clear(),
    ):
        with pytest.raises(TypeError, match="只读快照"):
            mutate()

    frozen_set = ConcurrentStableSet([1]).freeze()
    for mutate in (lambda: frozen_set.add(2), lambda: frozen_set.discard(1), lambda: frozen_set.clear()):
        with pytest.raises(TypeError, match="只读快照"):
            mutate()

    frozen_dict = ConcurrentStableDict({"a": 1}).freeze()
    for mutate in (
        lambda: frozen_dict.set("b", 2),
        lambda: frozen_dict.delete("a"),
        lambda: frozen_dict.clear(),
        lambda: frozen_dict.setdefault("c", 3),
    ):
        with pytest.raises(TypeError, match="只读快照"):
            mutate()
    assert frozen_dict.to_dict() == {"a": 1}


@pytest.mark.kiwi_id(2322)
def test_freeze_guards_sorted_forms() -> None:
    """升序形态同样受冻结保护（写守卫落在各形态的写路径上）。"""
    frozen_list = ConcurrentSortedList([1, 2]).freeze()
    with pytest.raises(TypeError, match="只读快照"):
        frozen_list.add(3)
    frozen_set = ConcurrentSortedSet([1]).freeze()
    with pytest.raises(TypeError, match="只读快照"):
        frozen_set.add(2)
    frozen_dict = ConcurrentSortedDict({"a": 1}).freeze()
    with pytest.raises(TypeError, match="只读快照"):
        frozen_dict.set("b", 2)


# ---------------- 升序形态同一套写法 ----------------


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", [LockStrategy.RW, LockStrategy.RLCK, LockStrategy.SNAPSHOT, LockStrategy.SHARDED])
def test_sorted_forms_mirror_stable_forms(strategy: LockStrategy) -> None:
    """升序形态同一套写法：列表 / 集合 / 字典的通用方法面与插入序形态同名同义。"""
    items = ConcurrentSortedList([2, 1], strategy=strategy)
    items.append(3)
    items.extend([0])
    items += [4]
    assert items.to_list() == [0, 1, 2, 3, 4]
    assert (items.__add__([5])).to_list() == [0, 1, 2, 3, 4, 5]
    assert items.pop() == 4
    items[0] = 9
    assert items.to_list() == [1, 2, 3, 9]
    del items[0]
    assert items.to_list() == [2, 3, 9]
    # 升序形态：`sorted` 结果落回底层后按升序归位（`reverse` 对升序形态无效，如实断言）
    assert items.sorted().to_list() == [2, 3, 9]
    assert items.sorted(reverse=True).to_list() == [2, 3, 9]
    assert items.copy().to_list() == [2, 3, 9]
    with pytest.raises(TypeError, match="重建集合"):
        items[cast("Any", slice(0, 1))] = 9
    with pytest.raises(TypeError, match="重建集合"):
        del items[cast("Any", slice(0, 1))]

    members = ConcurrentSortedSet([2, 1], strategy=strategy)
    members.remove(1)
    assert members.to_list() == [2]
    with pytest.raises(KeyError):
        members.remove(99)
    assert members.pop() == 2
    with pytest.raises(KeyError):
        members.pop()
    assert ConcurrentSortedSet([1, 2]).union([3]).to_list() == [1, 2, 3]
    assert ConcurrentSortedSet([1, 2]).intersection([2]).to_list() == [2]
    assert ConcurrentSortedSet([1, 2]).difference([2]).to_list() == [1]
    assert ConcurrentSortedSet([1, 2]).symmetric_difference([2, 3]).to_list() == [1, 3]
    sorted_clone = ConcurrentSortedSet([1, 2], strategy=strategy).copy()
    sorted_clone.add(3)
    assert sorted_clone.to_list() == [1, 2, 3]
    updated = ConcurrentSortedSet([1, 2])
    updated.update([3])
    updated.intersection_update([2, 3])
    updated.difference_update([2])
    updated.symmetric_difference_update([3, 4])
    assert updated.to_list() == [4]

    data = ConcurrentSortedDict[str, int]({"b": 2, "a": 1}, strategy=strategy)
    data["c"] = 3
    del data["b"]
    assert data.to_dict() == {"a": 1, "c": 3}
    data.update({"d": 4})
    data.update([("e", 5)])
    data.update(f=6)
    assert data.to_dict() == {"a": 1, "c": 3, "d": 4, "e": 5, "f": 6}
    assert data.pop("a") == 1
    assert data.pop("zzz", 0) == 0
    with pytest.raises(KeyError):
        data.pop("zzz")
    assert data.popitem() == ("f", 6)
    assert data.setdefault("g", 7) == 7
    assert data.setdefault("c", 99) == 3  # 既有键返回既有值（SHARDED 分支同样覆盖）
    assert data.sorted_items() == [("c", 3), ("d", 4), ("e", 5), ("g", 7)]
    assert data.sorted_items(key=lambda item: -item[1]) == [("g", 7), ("e", 5), ("d", 4), ("c", 3)]
    assert data.sorted_items(reverse=True) == [("g", 7), ("e", 5), ("d", 4), ("c", 3)]
    assert data.sorted_keys() == ["c", "d", "e", "g"]
    assert data.sorted_keys(reverse=True) == ["g", "e", "d", "c"]
    assert ConcurrentSortedDict[str, int].fromkeys(["x"], 0).to_dict() == {"x": 0}
    assert (data | {"h": 8}).to_dict()["h"] == 8
    data |= {"i": 9}
    assert data.get("i") == 9
    clone = data.copy()
    clone.set("j", 10)
    assert "j" not in data
    data.clear()
    assert data.to_dict() == {}
    with pytest.raises(KeyError):
        data.popitem()


@pytest.mark.kiwi_id(2322)
def test_sorted_dict_popitem_on_empty_non_sharded_raises() -> None:
    """升序字典非分段路径的空表 `popitem` 抛 KeyError（分支覆盖）。"""
    empty = ConcurrentSortedDict[str, int](strategy=LockStrategy.RW)
    with pytest.raises(KeyError):
        empty.popitem()


# ---------------- 并发安全 ----------------


@pytest.mark.kiwi_id(2322)
def test_write_sugar_is_thread_safe() -> None:
    """多线程写糖混写：元素不丢不重，每线程子序列保插入序。"""
    items = ConcurrentStableList[int]()
    thread_count = 4
    per_thread = 100
    barrier = threading.Barrier(thread_count)

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(per_thread):
            value = offset * 1000 + index
            if index % 3 == 0:
                items.append(value)
            elif index % 3 == 1:
                items.extend([value])
            else:
                items.__iadd__([value])

    threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = items.to_list()
    assert len(snapshot) == thread_count * per_thread
    for offset in range(thread_count):
        assert [value for value in snapshot if value // 1000 == offset] == [
            offset * 1000 + index for index in range(per_thread)
        ]


@pytest.mark.kiwi_id(2322)
def test_dict_and_set_sugar_thread_safe() -> None:
    """字典 / 集合的写糖与原子方法在多线程下不崩、结果正确。"""
    data = ConcurrentStableDict[int, int]()
    members = ConcurrentStableSet[int]()
    thread_count = 4
    per_thread = 50
    barrier = threading.Barrier(thread_count)

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(per_thread):
            key = offset * 1000 + index
            data[key] = index
            data.setdefault(key, -1)
            members.add(key)
            members.remove(key)
            members.add(key)

    threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(data) == thread_count * per_thread
    assert len(members) == thread_count * per_thread
    expected = {(offset * 1000 + index): index for offset in range(thread_count) for index in range(per_thread)}
    assert all(data.get(key) == value for key, value in expected.items())


# ---------------- 形态一致性 ----------------


@pytest.mark.kiwi_id(2322)
def test_both_forms_expose_same_general_surface() -> None:
    """两形态 API 不分叉：同一套通用方法名在插入序与升序形态上同时存在。"""
    list_methods = ("append", "extend", "pop", "sorted", "merge", "copy")
    set_methods = (
        "remove",
        "pop",
        "copy",
        "union",
        "intersection",
        "difference",
        "symmetric_difference",
        "update",
        "intersection_update",
        "difference_update",
        "symmetric_difference_update",
    )
    dict_methods = (
        "clear",
        "pop",
        "popitem",
        "setdefault",
        "fromkeys",
        "update",
        "copy",
        "sorted_items",
        "sorted_keys",
        "__setitem__",
        "__delitem__",
        "__or__",
        "__ior__",
    )
    for cls, names in (
        (ConcurrentStableList, list_methods),
        (ConcurrentSortedList, list_methods),
        (ConcurrentStableSet, set_methods),
        (ConcurrentSortedSet, set_methods),
        (ConcurrentStableDict, dict_methods),
        (ConcurrentSortedDict, dict_methods),
    ):
        for name in names:
            assert hasattr(cls, name), f"{cls.__name__} 缺 {name}"


@pytest.mark.kiwi_id(2322)
def test_no_full_reindexing_operations_on_lists() -> None:
    """禁用方法不存在：`insert` / 原地 `sort` / 原地 `reverse`（须全表重编号并持全局写锁）。"""
    for cls in (ConcurrentStableList, ConcurrentSortedList):
        for name in ("insert", "sort", "reverse"):
            assert not hasattr(cls, name), f"{cls.__name__} 不应提供 {name}"


@pytest.mark.kiwi_id(2322)
def test_deepcopy_rebuilds_independent_collection() -> None:
    """`__deepcopy__` 重建独立同类集合（元素深拷贝、锁不共享）。"""
    import copy as copy_module

    original: ConcurrentStableDict[str, ConcurrentStableList[int]] = ConcurrentStableDict(
        {"a": ConcurrentStableList([1, 2])}
    )
    cloned = copy_module.deepcopy(original)
    assert isinstance(cloned, ConcurrentStableDict)
    assert cloned.to_dict()["a"] == ConcurrentStableList([1, 2])
    cloned.set("b", ConcurrentStableList([3]))
    assert original.to_dict()["a"] == ConcurrentStableList([1, 2])


@pytest.mark.kiwi_id(2322)
def test_stale_seq_helpers_return_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """段内序号已不存在时 `_delete_seq` / `_replace_seq` 返回 False（并发删除窗口防御）。"""
    items: ConcurrentStableList[str] = ConcurrentStableList(["keep"])

    def fake_list_view(_self: object) -> list[tuple[int, str]]:  # bare-collections:allow 替身须返回内部结构
        """替身 `_view`：返回段内不存在的序号（模拟并发删除窗口）。"""
        return [(999_999, "ghost")]

    with monkeypatch.context() as patch:
        patch.setattr(ConcurrentStableList, "_view", fake_list_view)
        assert items.pop() == "ghost"
    # 私有助手直接在实例上调用（测试内验证并发窗口防御分支）
    assert items._delete_seq(999_999) is False  # pyright: ignore[reportPrivateUsage]
    assert items._replace_seq(999_999, "x") is False  # pyright: ignore[reportPrivateUsage]

    data: ConcurrentStableDict[str, int] = ConcurrentStableDict({"a": 1})

    def fake_dict_view(_self: object) -> list[tuple[str, int]]:  # bare-collections:allow 替身须返回内部结构
        """替身 `_view`：返回不存在的键（模拟并发窗口）。"""
        return [("ghost", 1)]

    with monkeypatch.context() as patch:
        patch.setattr(ConcurrentStableDict, "_view", fake_dict_view)
        data["ghost"] = 2  # 走 set 路径，不依赖 _view
    assert data.to_dict() == {"a": 1, "ghost": 2}


@pytest.mark.kiwi_id(2322)
def test_set_pop_walks_multiple_shards() -> None:
    """SHARDED 集合 `pop`：跨多段找最小序号、目标不在首段时继续找（分支覆盖）。"""
    members = ConcurrentStableSet([f"k{index}" for index in range(20)])
    popped = [members.pop() for _ in range(20)]
    assert popped == [f"k{index}" for index in range(20)]
    with pytest.raises(KeyError):
        members.pop()


@pytest.mark.kiwi_id(2322)
def test_set_pop_finds_element_outside_first_shard() -> None:
    """SHARDED 集合 `pop`：首个插入元素不在 0 号段时，删除循环继续遍历后续段（分支覆盖）。"""
    probe = next(value for value in (f"p{index}" for index in range(100)) if hash(value) % 16 != 0)
    probe_shard = hash(probe) % 16
    filler = next(value for value in (f"f{index}" for index in range(100)) if hash(value) % 16 != probe_shard)
    members = ConcurrentStableSet([probe, filler])
    assert members.pop() == probe
    assert members.to_list() == [filler]


@pytest.mark.kiwi_id(2322)
def test_empty_collection_key_errors_on_non_sharded_paths() -> None:
    """非分段策略下的空表异常分支：字典 `popitem` / 集合 `pop`。"""
    empty_dict = ConcurrentStableDict[str, int](strategy=LockStrategy.RW)
    with pytest.raises(KeyError):
        empty_dict.popitem()
    empty_set = ConcurrentStableSet[int](strategy=LockStrategy.RW)
    with pytest.raises(KeyError):
        empty_set.pop()


@pytest.mark.kiwi_id(2322)
@pytest.mark.parametrize("strategy", [LockStrategy.RW, LockStrategy.SHARDED])
def test_put_if_absent_writes_on_both_paths(strategy: LockStrategy) -> None:
    """`put_if_absent` 两条路径的写入分支（键不存在 → 写入并返回 None）。"""
    data = ConcurrentStableDict[str, int]({"a": 1}, strategy=strategy)
    assert data.put_if_absent("a", 9) == 1
    assert data.put_if_absent("b", 2) is None
    assert data.to_dict() == {"a": 1, "b": 2}


@pytest.mark.kiwi_id(2322)
def test_base_sorted_str_uses_json_payload() -> None:
    """公共段 `__str__` 走 `_json_data()`：映射输出 `{..}`、序列输出 `[..]`。"""
    assert issubclass(BaseSorted, BaseCollection)
    rendered = str(ConcurrentStableDict({"a": [1, 2]}))
    assert rendered == "ConcurrentStableDict({'a': [1, 2]})"


@pytest.mark.kiwi_id(2322)
def test_cross_replica_forms_reject_freeze() -> None:
    """跨副本形态与缓存快照**不支持 `freeze`**（无同步读入口，无法构造内容快照）。"""
    members = RedisSortedSet(None, "bms:global:demo:set")  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="不支持 freeze"):
        members.freeze()
    snapshot = RedisSnapshot(None, "bms:global:demo:v", lambda: None)  # type: ignore[arg-type]
    with pytest.raises(NotImplementedError, match="不支持 freeze"):
        snapshot.freeze()
