"""core 层进程内并发集合：原子复合方法与快照遍历。

- 锁策略与守卫见 app.core.locking（公共横切，可被其它模块复用）
- 遍历一律返回快照副本；跨副本共享见 app.core.redis_collections
"""

import heapq
import threading
from abc import abstractmethod
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar, cast

from app.core.base import ValueHolder
from app.core.collections import BaseSorted, SortedDict, SortedList, SortedSet
from app.core.locking import LockGuard, LockStrategy, ReadWriteLock

DataT = TypeVar("DataT")


class BaseConcurrentSorted[ItemT, DataT](BaseSorted[ItemT]):
    """进程内并发有序集合基类：锁策略守卫 + SNAPSHOT 写时复制模板。

    子类实现 `_copy_data`（复制内部数据）；读改写由 `_guard` 按策略加锁，
    SNAPSHOT 策略写时复制后替换，其余策略直接操作内部数据。
    """

    _guard: LockGuard
    _data: DataT

    def __init__(self, *, strategy: LockStrategy) -> None:
        self._guard = LockGuard(strategy)

    @abstractmethod
    def _copy_data(self) -> DataT:
        """复制内部数据（SNAPSHOT 策略写时复制）。"""

    @contextmanager
    def _write_data(self) -> Generator[DataT]:
        """写上下文：SNAPSHOT 写时复制，其余直接操作内部数据。"""
        with self._guard.write():
            snapshot = self._guard.strategy is LockStrategy.SNAPSHOT
            data = self._copy_data() if snapshot else self._data
            yield data
            if snapshot:
                self._data = data


class ConcurrentSortedList[ItemT](BaseConcurrentSorted[ItemT, SortedList[ItemT]]):
    """并发有序列表：RW（默认）/ RLCK / SNAPSHOT；SHARDED 自动降级为 RW。"""

    def __init__(
        self,
        items: Iterable[ItemT] = (),
        *,
        strategy: LockStrategy = LockStrategy.RW,
        key: Callable[[ItemT], object] | None = None,
    ) -> None:
        effective = LockStrategy.RW if strategy is LockStrategy.SHARDED else strategy
        super().__init__(strategy=effective)
        self._key = key
        self._data = SortedList(items, key=key)

    def _copy_data(self) -> SortedList[ItemT]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return SortedList(self._data, key=self._key)

    def add(self, item: ItemT) -> None:
        """插入元素。"""
        with self._write_data() as data:
            data.add(item)

    def update(self, items: Iterable[ItemT]) -> None:
        """批量插入。"""
        with self._write_data() as data:
            data.update(items)

    def discard(self, item: ItemT) -> None:
        """删除元素（不存在不报错）。"""
        with self._write_data() as data:
            data.discard(item)

    def remove(self, item: ItemT) -> None:
        """删除元素（不存在抛 ValueError）。"""
        with self._write_data() as data:
            data.remove(item)

    def clear(self) -> None:
        """清空。"""
        with self._write_data() as data:
            data.clear()

    def to_list(self) -> list[ItemT]:
        """有序元素列表（快照）。"""
        with self._guard.read():
            return list(self._data)

    def _json_data(self) -> object:
        return self.to_list()

    def __contains__(self, item: object) -> bool:
        with self._guard.read():
            return item in self._data

    def __len__(self) -> int:
        with self._guard.read():
            return len(self._data)

    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.to_list())


class ConcurrentSortedSet[ItemT](BaseConcurrentSorted[ItemT, SortedSet[ItemT]]):
    """并发有序集合：RW（默认）/ RLCK / SHARDED / SNAPSHOT。"""

    def __init__(
        self,
        items: Iterable[ItemT] = (),
        *,
        strategy: LockStrategy = LockStrategy.RW,
        shard_count: int = 16,
    ) -> None:
        if strategy is LockStrategy.SHARDED:
            if shard_count < 1:
                raise ValueError("shard_count 必须 ≥ 1")
            self._global = ReadWriteLock()
            self._shards: list[tuple[threading.RLock, SortedSet[ItemT]]] = [
                (threading.RLock(), SortedSet()) for _ in range(shard_count)
            ]
        else:
            self._shards = []
        super().__init__(strategy=strategy if strategy is not LockStrategy.SHARDED else LockStrategy.RW)
        self._strategy = strategy
        materialized = list(items)
        self._data = SortedSet(materialized)
        if self._strategy is LockStrategy.SHARDED:
            for item in materialized:
                self._shards[hash(item) % len(self._shards)][1].add(item)

    def _shard(self, item: ItemT) -> tuple[threading.RLock, SortedSet[ItemT]] | None:
        if self._strategy is LockStrategy.SHARDED:
            return self._shards[hash(item) % len(self._shards)]
        return None

    def _view(self) -> list[ItemT]:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshots = [list(data) for _, data in self._shards]
            streams = cast("list[Iterable[Any]]", snapshots)
            return list(cast("Iterator[ItemT]", heapq.merge(*streams)))
        with self._guard.read():
            return list(self._data)

    def _copy_data(self) -> SortedSet[ItemT]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return SortedSet(self._data)

    def add(self, item: ItemT) -> None:
        """插入元素（去重）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                data.add(item)
            return
        with self._write_data() as data:
            data.add(item)

    def add_if_absent(self, item: ItemT) -> bool:
        """不存在才插入，返回是否新增（原子）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if item in data:
                    return False
                data.add(item)
                return True
        with self._write_data() as data:
            if item in data:
                return False
            data.add(item)
            return True

    def discard(self, item: ItemT) -> None:
        """删除元素（不存在不报错）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                data.discard(item)
            return
        with self._write_data() as data:
            data.discard(item)

    def remove_atomic(self, item: ItemT) -> bool:
        """删除元素并返回是否删除（原子）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if item not in data:
                    return False
                data.discard(item)
                return True
        with self._write_data() as data:
            if item not in data:
                return False
            data.discard(item)
            return True

    def clear(self) -> None:
        """清空。"""
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                for _, data in self._shards:
                    data.clear()
            return
        with self._write_data() as data:
            data.clear()

    def to_list(self) -> list[ItemT]:
        """有序元素列表（快照）。"""
        return self._view()

    def _json_data(self) -> object:
        return self.to_list()

    def __contains__(self, item: object) -> bool:
        shard = self._shard(item)  # type: ignore[arg-type]  # 分片哈希对 object 安全
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return item in data
        with self._guard.read():
            return item in self._data

    def __len__(self) -> int:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                return sum(len(data) for _, data in self._shards)
        with self._guard.read():
            return len(self._data)

    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.to_list())


class ConcurrentSortedDict[KeyT, ValueT](BaseConcurrentSorted[tuple[KeyT, ValueT], SortedDict[KeyT, ValueT]]):
    """并发有序字典：RW（默认）/ RLCK / SHARDED / SNAPSHOT。"""

    def __init__(
        self,
        items: Mapping[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]] = (),
        *,
        strategy: LockStrategy = LockStrategy.RW,
        shard_count: int = 16,
    ) -> None:
        if strategy is LockStrategy.SHARDED:
            if shard_count < 1:
                raise ValueError("shard_count 必须 ≥ 1")
            self._global = ReadWriteLock()
            self._shards: list[tuple[threading.RLock, SortedDict[KeyT, ValueT]]] = [
                (threading.RLock(), SortedDict()) for _ in range(shard_count)
            ]
        else:
            self._shards = []
        super().__init__(strategy=strategy if strategy is not LockStrategy.SHARDED else LockStrategy.RW)
        self._strategy = strategy
        entries: list[tuple[KeyT, ValueT]] = (
            list(cast("Mapping[KeyT, ValueT]", items).items()) if isinstance(items, Mapping) else list(items)
        )
        self._data = SortedDict(entries)
        if self._strategy is LockStrategy.SHARDED:
            for key, value in entries:
                self._shards[hash(key) % len(self._shards)][1][key] = value

    def _shard(self, key: KeyT) -> tuple[threading.RLock, SortedDict[KeyT, ValueT]] | None:
        if self._strategy is LockStrategy.SHARDED:
            return self._shards[hash(key) % len(self._shards)]
        return None

    def _view(self) -> list[tuple[KeyT, ValueT]]:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshots = [data.to_list() for _, data in self._shards]
            streams = cast("list[Iterable[Any]]", snapshots)
            return list(cast("Iterator[tuple[KeyT, ValueT]]", heapq.merge(*streams)))
        with self._guard.read():
            return self._data.to_list()

    def _copy_data(self) -> SortedDict[KeyT, ValueT]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return SortedDict(self._data)

    def set(self, key: KeyT, value: ValueT) -> None:
        """写入键值。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                data[key] = value
            return
        with self._write_data() as data:
            data[key] = value

    def get(self, key: KeyT) -> ValueT | None:
        """按键取值（不存在返回 None）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.get(key)
        with self._guard.read():
            return self._data.get(key)

    def delete(self, key: KeyT) -> None:
        """删除键（不存在抛 KeyError）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                del data[key]
            return
        with self._write_data() as data:
            del data[key]

    def put_if_absent(self, key: KeyT, value: ValueT) -> ValueT | None:
        """不存在才写入，返回既有值或 None（原子）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if key in data:
                    return data[key]
                data[key] = value
                return None
        with self._write_data() as data:
            if key in data:
                return data[key]
            data[key] = value
            return None

    def update_atomic(self, key: KeyT, func: Callable[[ValueT], ValueT]) -> ValueT:
        """原子更新（func 必须纯计算、禁 IO）；键不存在抛 KeyError。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                value = func(data[key])
                data[key] = value
                return value
        with self._write_data() as data:
            value = func(data[key])
            data[key] = value
            return value

    def remove_atomic(self, key: KeyT) -> ValueT:
        """删除并返回旧值（原子）；键不存在抛 KeyError。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                value = data[key]
                del data[key]
                return value
        with self._write_data() as data:
            value = data[key]
            del data[key]
            return value

    def replace_if_equal(self, key: KeyT, expected: ValueT, new: ValueT) -> bool:
        """CAS：当前值等于 expected 才替换（原子）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if key in data and data[key] == expected:
                    data[key] = new
                    return True
                return False
        with self._write_data() as data:
            if key in data and data[key] == expected:
                data[key] = new
                return True
            return False

    def get_and_remove(self, key: KeyT) -> ValueT | None:
        """取走并删除，返回旧值或 None（原子）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if key not in data:
                    return None
                value = data[key]
                del data[key]
                return value
        with self._write_data() as data:
            if key not in data:
                return None
            value = data[key]
            del data[key]
            return value

    @contextmanager
    def get_locked(self, key: KeyT) -> Generator[ValueHolder[ValueT]]:
        """锁内读改写上下文（复杂复合逻辑；holder.value 写回）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                holder = ValueHolder(data[key])
                yield holder
                data[key] = holder.value
            return
        with self._write_data() as data:
            holder = ValueHolder(data[key])
            yield holder
            data[key] = holder.value

    def to_list(self) -> list[tuple[KeyT, ValueT]]:
        """有序键值对列表（快照）。"""
        return self._view()

    def to_dict(self) -> dict[KeyT, ValueT]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """键序字典（快照）。"""
        return dict(self._view())

    def _json_data(self) -> object:
        return self.to_dict()

    def __contains__(self, key: object) -> bool:
        shard = self._shard(key)  # type: ignore[arg-type]  # 分片哈希对 object 安全
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return key in data
        with self._guard.read():
            return key in self._data

    def __len__(self) -> int:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                return sum(len(data) for _, data in self._shards)
        with self._guard.read():
            return len(self._data)

    def __iter__(self) -> Iterator[tuple[KeyT, ValueT]]:
        return iter(self.to_list())
