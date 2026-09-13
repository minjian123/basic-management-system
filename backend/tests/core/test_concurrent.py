"""进程内并发集合测试（Kiwi 16）。"""

import threading

import pytest

from app.core.base import BaseObject
from app.core.collections import BaseSorted
from app.core.concurrent import (
    BaseConcurrentSorted,
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
    LockStrategy,
    ReadWriteLock,
)

STRATEGIES = [LockStrategy.RW, LockStrategy.RLCK, LockStrategy.SHARDED, LockStrategy.SNAPSHOT]


@pytest.mark.kiwi_id(16)
def test_read_write_lock_is_mutually_exclusive() -> None:
    """读写互斥：写锁下读等待、读锁下写等待（写优先）。"""
    lock = ReadWriteLock()
    reader_entered = threading.Event()

    def read_once() -> None:
        with lock.read():
            reader_entered.set()

    with lock.write():
        reader = threading.Thread(target=read_once)
        reader.start()
        assert not reader_entered.wait(0.05)
    reader.join(1)
    assert reader_entered.is_set()

    writer_entered = threading.Event()

    def write_once() -> None:
        with lock.write():
            writer_entered.set()

    with lock.read():
        writer = threading.Thread(target=write_once)
        writer.start()
        assert not writer_entered.wait(0.05)
    writer.join(1)
    assert writer_entered.is_set()


@pytest.mark.kiwi_id(16)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_concurrent_list_behaviour(strategy: LockStrategy) -> None:
    """并发列表各策略行为一致（含 SHARDED 自动降级）。"""
    items = ConcurrentSortedList([3, 1], strategy=strategy)
    items.add(2)
    items.update([4, 0])
    assert items.to_list() == [0, 1, 2, 3, 4]
    assert 2 in items
    assert len(items) == 5
    assert list(iter(items)) == [0, 1, 2, 3, 4]
    assert items.to_json() == "[0, 1, 2, 3, 4]"
    items.discard(0)
    assert 0 not in items
    items.remove(4)
    items.clear()
    assert items.to_list() == []


@pytest.mark.kiwi_id(16)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_concurrent_set_behaviour(strategy: LockStrategy) -> None:
    """并发集合各策略行为一致（原子新增/删除）。"""
    items = ConcurrentSortedSet([2, 1], strategy=strategy)
    items.add(3)
    assert items.add_if_absent(3) is False
    assert items.add_if_absent(4) is True
    assert list(items) == [1, 2, 3, 4]
    assert items.to_list() == [1, 2, 3, 4]
    assert items.to_json() == "[1, 2, 3, 4]"
    assert 3 in items
    assert 99 not in items
    assert len(items) == 4
    items.discard(4)
    assert items.remove_atomic(4) is False
    assert items.remove_atomic(3) is True
    assert str(items).startswith("ConcurrentSortedSet(")
    items.clear()
    assert len(items) == 0


@pytest.mark.kiwi_id(16)
def test_concurrent_set_rejects_bad_shard_count() -> None:
    """分片数必须 ≥ 1。"""
    with pytest.raises(ValueError):
        ConcurrentSortedSet(strategy=LockStrategy.SHARDED, shard_count=0)
    with pytest.raises(ValueError):
        ConcurrentSortedDict(strategy=LockStrategy.SHARDED, shard_count=0)


@pytest.mark.kiwi_id(16)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_concurrent_dict_behaviour(strategy: LockStrategy) -> None:
    """并发字典各策略行为一致（读写/序列化/删除）。"""
    data = ConcurrentSortedDict({"b": 2, "a": 1}, strategy=strategy)
    data.set("c", 3)
    assert data.get("a") == 1
    assert data.get("zzz") is None
    assert "a" in data
    assert "zzz" not in data
    assert data.to_list() == [("a", 1), ("b", 2), ("c", 3)]
    assert data.to_dict() == {"a": 1, "b": 2, "c": 3}
    assert data.to_json() == '{"a": 1, "b": 2, "c": 3}'
    assert repr(data).startswith("ConcurrentSortedDict(")
    assert list(iter(data)) == [("a", 1), ("b", 2), ("c", 3)]
    assert len(data) == 3
    data.delete("c")
    assert "c" not in data


@pytest.mark.kiwi_id(16)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_concurrent_dict_atomic_methods(strategy: LockStrategy) -> None:
    """原子复合方法：并发读改写不错乱（含缺失分支）。"""
    data = ConcurrentSortedDict({"a": 1}, strategy=strategy)
    assert data.put_if_absent("a", 9) == 1
    assert data.put_if_absent("b", 2) is None
    assert data.update_atomic("a", lambda value: value + 1) == 2
    assert data.replace_if_equal("a", 2, 7) is True
    assert data.replace_if_equal("a", 999, 8) is False
    assert data.replace_if_equal("zzz", 1, 2) is False
    assert data.get_and_remove("b") == 2
    assert data.get_and_remove("b") is None
    assert data.remove_atomic("a") == 7

    data.set("c", 1)
    with data.get_locked("c") as holder:
        holder.value = holder.value + 10
    assert data.get("c") == 11

    with pytest.raises(KeyError):
        data.remove_atomic("zzz")
    with pytest.raises(KeyError):
        data.update_atomic("zzz", lambda value: value)
    with pytest.raises(KeyError):
        data.delete("zzz")
    with pytest.raises(KeyError), data.get_locked("zzz"):
        pass


@pytest.mark.kiwi_id(16)
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_concurrent_safety_under_threads(strategy: LockStrategy) -> None:
    """多线程混合读写：不丢不重、最终一致。"""
    data = ConcurrentSortedDict[str, int]({}, strategy=strategy)
    thread_count = 4
    per_thread = 100
    barrier = threading.Barrier(thread_count)

    def worker(offset: int) -> None:
        barrier.wait()
        for index in range(per_thread):
            key = f"{offset}-{index}"
            data.set(key, index)
            data.update_atomic(key, lambda value: value + 1)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(data) == thread_count * per_thread
    expected = {(f"{offset}-{index}"): index + 1 for offset in range(thread_count) for index in range(per_thread)}
    assert all(data.get(key) == value for key, value in expected.items())


@pytest.mark.kiwi_id(16)
def test_snapshot_reader_keeps_immutable_view() -> None:
    """快照策略：读者拿到旧引用不受后续写入影响。"""
    data = ConcurrentSortedDict({"a": 1}, strategy=LockStrategy.SNAPSHOT)
    snapshot = data.to_dict()
    data.set("b", 2)
    assert snapshot == {"a": 1}
    assert data.to_dict() == {"a": 1, "b": 2}


@pytest.mark.kiwi_id(16)
def test_concurrent_sorted_inherit_base_concurrent_sorted() -> None:
    """并发集合继承链：ConcurrentSorted* → BaseConcurrentSorted → BaseSorted → BaseObject。"""
    assert issubclass(BaseConcurrentSorted, BaseSorted)
    assert issubclass(BaseSorted, BaseObject)
    assert issubclass(ConcurrentSortedList, BaseConcurrentSorted)
    assert issubclass(ConcurrentSortedSet, BaseConcurrentSorted)
    assert issubclass(ConcurrentSortedDict, BaseConcurrentSorted)
