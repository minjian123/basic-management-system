"""插入序并发集合与只读 API 测试（Kiwi 2222：插入序形态与并发）。

覆盖：插入序形态继承链与 `collection_kind`；不可比较元素的插入序稳定输出；
`SHARDED` 分段写 + 插入序号归并（多线程并发写后读回插入序）；`Sequence` / `Mapping` /
`Set` 只读面（索引 / 切片 / `keys` / `items` / 集合运算 / 与内置容器相等）；写入仅走显式原子方法。
"""

import threading
from collections.abc import Mapping, Sequence, Set

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.collections import BaseSorted
from bms_core.core.concurrent import (
    BaseConcurrent,
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.locking import LockStrategy
from bms_core.core.sorted_collections import (
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
)

STABLE_STRATEGIES = [LockStrategy.SHARDED, LockStrategy.RW, LockStrategy.RLCK, LockStrategy.SNAPSHOT]


class _Uncomparable:
    """不可比较元素（无 `<` 语义，只按身份相等）：验证插入序形态不比较元素。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    def __repr__(self) -> str:
        return f"_Uncomparable({self.tag!r})"


@pytest.mark.kiwi_id(2222)
def test_stable_inherit_chain_and_kind() -> None:
    """插入序形态接入集合体系同步链，并以 `collection_kind="stable"` 区分。"""
    for member in (ConcurrentStableList, ConcurrentStableSet, ConcurrentStableDict):
        assert issubclass(member, BaseConcurrent)
        assert member.collection_kind == "stable"
    assert issubclass(BaseConcurrent, BaseSorted)
    assert issubclass(BaseSorted, BaseObject)
    assert issubclass(ConcurrentStableList, Sequence)
    assert issubclass(ConcurrentStableSet, Set)
    assert issubclass(ConcurrentStableDict, Mapping)


@pytest.mark.kiwi_id(2222)
@pytest.mark.parametrize("strategy", STABLE_STRATEGIES)
def test_stable_list_insertion_order_with_uncomparable_items(strategy: LockStrategy) -> None:
    """列表保插入序、不比较元素；只读面（索引 / 切片 / 查找 / 反转 / 相等）可用。"""
    payload = [_Uncomparable(f"n{index}") for index in range(50)]
    items = ConcurrentStableList(payload, strategy=strategy)
    tail = _Uncomparable("tail")
    items.add(tail)
    assert [entry.tag for entry in items] == [*(f"n{index}" for index in range(50)), "tail"]
    assert len(items) == 51
    assert items[0] is payload[0]
    assert items[-1] is tail
    assert items[1:3] == payload[1:3]
    assert items.index(payload[3]) == 3
    assert items.count(payload[3]) == 1
    assert next(reversed(items)) is tail
    assert list(reversed(items))[:2] == [tail, payload[-1]]
    assert "_Uncomparable('n0')" in items.to_json()
    items.discard(payload[0])
    assert payload[0] not in items
    items.remove(payload[1])
    with pytest.raises(ValueError):
        items.remove(payload[1])
    items.clear()
    assert items.to_list() == []


@pytest.mark.kiwi_id(2222)
@pytest.mark.parametrize("strategy", STABLE_STRATEGIES)
def test_stable_set_insertion_order_and_dedup(strategy: LockStrategy) -> None:
    """集合保插入序 + 去重、不比较元素；集合运算返回同类且保插入序。"""
    first, second = _Uncomparable("a"), _Uncomparable("b")
    items = ConcurrentStableSet([first, second], strategy=strategy)
    third = _Uncomparable("c")
    assert items.add_if_absent(first) is False
    assert items.add_if_absent(third) is True
    assert items.to_list() == [first, second, third]
    assert first in items
    assert _Uncomparable("a") not in items
    assert len(items) == 3
    fourth = _Uncomparable("d")
    assert (items & ConcurrentStableSet([second, third])) == {second, third}
    assert (items | ConcurrentStableSet([fourth])).to_list() == [first, second, third, fourth]
    assert (items - ConcurrentStableSet([second])).to_list() == [first, third]
    assert (items ^ ConcurrentStableSet([second, fourth])).to_list() == [first, third, fourth]
    assert items == {first, second, third}
    assert items.remove_atomic(second) is True
    assert items.remove_atomic(second) is False
    items.discard(third)
    assert third not in items


@pytest.mark.kiwi_id(2222)
@pytest.mark.parametrize("strategy", STABLE_STRATEGIES)
def test_stable_dict_insertion_order(strategy: LockStrategy) -> None:
    """字典保插入序、不比较键；更新已存在键保持原插入位置；原子方法语义不变。"""
    data = ConcurrentStableDict[str, int]({}, strategy=strategy)
    data.set("b", 2)
    data.set("a", 1)
    data.set("c", 3)
    assert data.to_list() == [("b", 2), ("a", 1), ("c", 3)]
    assert data["a"] == 1
    assert data.get("a") == 1
    assert data.get("zzz") is None
    assert data.get("zzz", 7) == 7
    assert list(data) == ["b", "a", "c"]
    assert list(data.keys()) == ["b", "a", "c"]
    assert list(data.items()) == [("b", 2), ("a", 1), ("c", 3)]
    assert list(data.values()) == [2, 1, 3]
    assert data == {"a": 1, "b": 2, "c": 3}
    assert data.to_json() == '{"a": 1, "b": 2, "c": 3}'
    data.set("b", 20)
    assert data.to_list() == [("b", 20), ("a", 1), ("c", 3)]
    assert data.put_if_absent("a", 9) == 1
    assert data.update_atomic("a", lambda value: value + 1) == 2
    assert data.replace_if_equal("a", 2, 7) is True
    assert data.replace_if_equal("a", 999, 8) is False
    assert data.get_and_remove("c") == 3
    with data.get_locked("b") as holder:
        holder.value += 1
    assert data.get("b") == 21
    assert data.remove_atomic("b") == 21
    assert len(data) == 1
    with pytest.raises(KeyError):
        _ = data["zzz"]


@pytest.mark.kiwi_id(2222)
def test_stable_rejects_bad_shard_count() -> None:
    """分段数必须 ≥ 1。"""
    with pytest.raises(ValueError):
        ConcurrentStableList(strategy=LockStrategy.SHARDED, shard_count=0)
    with pytest.raises(ValueError):
        ConcurrentStableSet(strategy=LockStrategy.SHARDED, shard_count=0)
    with pytest.raises(ValueError):
        ConcurrentStableDict(strategy=LockStrategy.SHARDED, shard_count=0)


@pytest.mark.kiwi_id(2222)
def test_stable_write_only_via_explicit_methods() -> None:
    """写入仅走显式原子方法：不提供 `append` / `__setitem__`。"""
    list_instance = ConcurrentStableList([1, 2])
    set_instance = ConcurrentStableSet([1, 2])
    dict_instance = ConcurrentStableDict[str, int]({"a": 1})
    for instance in (list_instance, set_instance, dict_instance):
        assert not hasattr(instance, "append")
        assert not hasattr(instance, "__setitem__")


@pytest.mark.kiwi_id(2222)
def test_stable_sharded_concurrent_write_restores_insertion_order() -> None:
    """SHARDED 分段写：多线程并发写后读回，元素不丢不重且每线程子序列保插入序。"""
    data = ConcurrentStableList[int]()
    thread_count = 8
    per_thread = 200
    barrier = threading.Barrier(thread_count)

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(per_thread):
            data.add(offset * 1000 + index)

    threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    snapshot = data.to_list()
    assert len(snapshot) == thread_count * per_thread
    assert sorted(snapshot) == [offset * 1000 + index for offset in range(thread_count) for index in range(per_thread)]
    for offset in range(thread_count):
        assert [value for value in snapshot if value // 1000 == offset] == [
            offset * 1000 + index for index in range(per_thread)
        ]


@pytest.mark.kiwi_id(2222)
def test_stable_dict_sharded_concurrent_write_restores_insertion_order() -> None:
    """SHARDED 分段写：并发行写入后每线程键序仍为插入序，读写不丢不重。"""
    data = ConcurrentStableDict[int, int]()
    thread_count = 8
    per_thread = 200
    barrier = threading.Barrier(thread_count)

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(per_thread):
            data.set(offset * 1000 + index, index)

    threads = [threading.Thread(target=worker, args=(offset,)) for offset in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(data) == thread_count * per_thread
    keys = list(data)
    for offset in range(thread_count):
        assert [key for key in keys if key // 1000 == offset] == [offset * 1000 + index for index in range(per_thread)]


@pytest.mark.kiwi_id(2222)
def test_sorted_read_only_api_mirrors_builtin_containers() -> None:
    """升序形态（基座内部实现）同样补齐只读 API，与内置容器内容相等。"""
    items = ConcurrentSortedList([3, 1, 2])
    assert items[0] == 1
    assert items[-1] == 3
    assert items[1:3] == [2, 3]
    assert items == [1, 2, 3]
    assert items.index(2) == 1
    assert items.count(2) == 1
    assert list(reversed(items)) == [3, 2, 1]

    data = ConcurrentSortedDict({"b": 2, "a": 1})
    assert data["a"] == 1
    assert list(data) == ["a", "b"]
    assert list(data.keys()) == ["a", "b"]
    assert list(data.items()) == [("a", 1), ("b", 2)]
    assert list(data.values()) == [1, 2]
    assert data == {"a": 1, "b": 2}

    members = ConcurrentSortedSet([2, 1])
    assert 1 in members
    assert len(members) == 2
    assert members == {1, 2}
    assert (members & {2, 3}) == {2}
    assert (members | {3}) == {1, 2, 3}
    assert (members - {1}) == {2}
    assert (members ^ {2, 3}) == {1, 3}
