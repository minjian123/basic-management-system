"""core 层进程内并发集合：原子复合方法与快照遍历。

- 锁策略与守卫见 bms_core.core.locking（公共横切，可被其它模块复用）
- 遍历一律返回快照副本；跨副本共享见 bms_core.core.redis_collections
- 插入序形态（`ConcurrentStable*`）以**分段写 + 插入序号归并**支持高并发写，是业务与契约的唯一落点；
  升序形态（`ConcurrentSorted*`）为基座内部实现（业务与契约不得直接声明 / 继承，排序走排序契约）
"""

import copy
import heapq
import threading
from abc import abstractmethod
from collections.abc import (
    Callable,
    Generator,
    ItemsView,
    Iterable,
    Iterator,
    KeysView,
    Mapping,
    Sequence,
    Set,
    ValuesView,
)
from contextlib import contextmanager
from typing import Any, ClassVar, Self, SupportsIndex, TypeVar, cast, overload

from bms_core.core.base import BaseObject
from bms_core.core.collections import BaseSorted, SortedDict, SortedList, SortedSet
from bms_core.core.holder import ValueHolder
from bms_core.core.locking import LockGuard, LockStrategy, ReadWriteLock

DataT = TypeVar("DataT")
DefaultT = TypeVar("DefaultT")
"""`get` 默认值类型（缺省分支返回 `ValueT | DefaultT`）。"""

_MAX_INDEX = 9223372036854775807
"""`Sequence.index` 的默认上界（与内置序列一致，避免 `None` 与 `SupportsIndex` 冲突）。"""


class BaseConcurrent[ItemT, DataT](BaseSorted[ItemT]):
    """基础并发层：锁策略守卫 + SNAPSHOT 写时复制模板（`BaseSorted` 之并发子层）。

    子类实现 `_copy_data`（复制内部数据）；读改写由 `_guard` 按策略加锁，
    SNAPSHOT 策略写时复制后替换，其余策略直接操作内部数据。

    分段（`SHARDED`）形态另行维护「全局读写锁（整表快照）+ 每段独立锁」，
    并把插入序号归并还原插入序；详见 `ConcurrentStable*`。
    """

    collection_kind: ClassVar[str] = "sorted_concurrent"

    _guard: LockGuard
    _data: DataT

    def __init__(self, *, strategy: LockStrategy) -> None:
        self._guard = LockGuard(strategy)

    @abstractmethod
    def _copy_data(self) -> DataT:
        """复制内部数据（SNAPSHOT 策略写时复制）。"""

    def __copy__(self) -> Self:
        """浅复制：按内容重建同类集合（锁不共享）。

        Returns:
            Self: 同类集合（内容快照）。
        """
        constructor = cast("Callable[[Iterable[Any]], Self]", type(self))
        return constructor(self.to_list())

    def __deepcopy__(self, memo: dict[int, Any]) -> Self:
        """深复制：元素深拷贝后重建同类集合（锁不共享；支持配置 / 契约深拷贝场景）。

        Args:
            memo: 深拷贝对象表。

        Returns:
            Self: 同类集合（元素深拷贝）。
        """
        constructor = cast("Callable[[Iterable[Any]], Self]", type(self))
        clone = constructor(copy.deepcopy(self.to_list(), memo))
        memo[id(self)] = clone
        return clone

    @contextmanager
    def _write_data(self) -> Generator[DataT]:
        """写上下文：SNAPSHOT 写时复制，其余直接操作内部数据。"""
        with self._guard.write():
            snapshot = self._guard.strategy is LockStrategy.SNAPSHOT
            data = self._copy_data() if snapshot else self._data
            yield data
            if snapshot:
                self._data = data


class ConcurrentSortedList[ItemT](BaseConcurrent[ItemT, SortedList[ItemT]], Sequence[ItemT]):
    """并发有序列表：RW（默认）/ RLCK / SNAPSHOT；SHARDED 自动降级为 RW。

    只读面按 `Sequence` 提供（索引 / 切片 / 相等），写入走显式原子方法；
    排序需求走排序契约（业务与契约不得直接声明本类）。
    """

    def __init__(
        self,
        items: Iterable[ItemT] = (),
        *,
        strategy: LockStrategy = LockStrategy.RW,
    ) -> None:
        effective = LockStrategy.RW if strategy is LockStrategy.SHARDED else strategy
        super().__init__(strategy=effective)
        self._data = SortedList(items)

    def _copy_data(self) -> SortedList[ItemT]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return SortedList(self._data)

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

    @overload
    def __getitem__(self, index: SupportsIndex) -> ItemT: ...

    @overload
    def __getitem__(self, index: slice) -> Self: ...

    def __getitem__(self, index: SupportsIndex | slice) -> ItemT | Self:
        snapshot = self.to_list()
        if isinstance(index, slice):
            return type(self)(snapshot[index])
        return snapshot[index]

    def index(self, value: Any, start: SupportsIndex = 0, stop: SupportsIndex = _MAX_INDEX, /) -> int:
        """元素首次出现的位置（快照内查找）。"""
        return self.to_list().index(value, int(start), int(stop))

    def count(self, value: Any, /) -> int:
        """元素出现次数（快照内统计）。"""
        return self.to_list().count(value)

    def __reversed__(self) -> Iterator[ItemT]:
        return reversed(self.to_list())

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `list` / `tuple` 及同类集合按元素比较。"""
        if isinstance(other, (list, tuple)):
            return self.to_list() == list(cast("Iterable[Any]", other))
        if isinstance(other, (ConcurrentSortedList, ConcurrentStableList)):
            return self.to_list() == list(cast("Iterable[Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentSortedSet[ItemT](BaseConcurrent[ItemT, SortedSet[ItemT]], Set[ItemT]):
    """并发有序集合：RW（默认）/ RLCK / SHARDED / SNAPSHOT。

    只读面按 `Set` 提供（成员判断 / 集合运算 / 相等），写入走显式原子方法；
    业务与契约不得直接声明本类（升序形态为基座内部实现）。
    """

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

    def __and__(self, other: Set[Any]) -> Self:
        """交集（返回同类，保本实例插入序）。"""
        return type(self)(item for item in self if item in other)

    def __or__(self, other: Set[Any]) -> Self:
        """并集（返回同类，先本实例元素、再 other 新增元素）。"""
        result = type(self)(self)
        for item in other:
            if item not in result:
                result.add(item)
        return result

    def __sub__(self, other: Set[Any]) -> Self:
        """差集（返回同类，保本实例插入序）。"""
        return type(self)(item for item in self if item not in other)

    def __xor__(self, other: Set[Any]) -> Self:
        """对称差集（返回同类，先本实例独有、再 other 独有）。"""
        result = type(self)(item for item in self if item not in other)
        for item in other:
            if item not in self:
                result.add(item)
        return result

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `set` / `frozenset` 及同类集合按元素比较（忽略顺序）。"""
        if isinstance(other, Set):
            return set(self) == set(cast("Set[Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentSortedDict[KeyT, ValueT](
    BaseConcurrent[tuple[KeyT, ValueT], SortedDict[KeyT, ValueT]], Mapping[KeyT, ValueT]
):
    """并发有序字典：RW（默认）/ RLCK / SHARDED / SNAPSHOT。

    只读面按 `Mapping` 提供（`[k]` / `keys` / `items` / `values` / 相等，`__iter__` 遍历键），
    写入走显式原子方法；业务与契约不得直接声明本类（升序形态为基座内部实现）。
    """

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

    @overload
    def get(self, key: KeyT) -> ValueT | None: ...

    @overload
    def get(self, key: KeyT, default: DefaultT) -> ValueT | DefaultT: ...

    def get(self, key: KeyT, default: Any = None) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        """按键取值（不存在返回 default，默认 None）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.get(key, default)
        with self._guard.read():
            return self._data.get(key, default)

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

    def __getitem__(self, key: KeyT) -> ValueT:
        """按键取值（不存在抛 KeyError）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data[key]
        with self._guard.read():
            return self._data[key]

    def keys(self) -> KeysView[KeyT]:
        """键视图（快照上构建，遍历安全）。"""
        return dict(self._view()).keys()

    def items(self) -> ItemsView[KeyT, ValueT]:
        """键值对视图（快照上构建，遍历安全）。"""
        return dict(self._view()).items()

    def values(self) -> ValuesView[ValueT]:
        """值视图（快照上构建，遍历安全）。"""
        return dict(self._view()).values()

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

    def __iter__(self) -> Iterator[KeyT]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """遍历键（Mapping 协议；键值对遍历走 `to_list()` / `items()`）。"""
        return iter(self.keys())

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `dict` / 映射及同类集合按键值比较（忽略顺序）。"""
        if isinstance(other, Mapping):
            return dict(self._view()) == dict(cast("Mapping[Any, Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentStableList[ItemT](BaseConcurrent[ItemT, list[tuple[int, ItemT]]], Sequence[ItemT]):
    """并发**插入序**列表：写入保插入序、不比较元素；默认分段写（`SHARDED`）。

    业务与契约的唯一列表落点。内部按插入序号（`seq`）分派段，段内已按序号有序，
    读 / 遍历按整数序号归并还原全局插入序；写入仍走显式原子方法（无 `append`）。
    """

    collection_kind: ClassVar[str] = "stable"

    def __init__(
        self,
        items: Iterable[ItemT] = (),
        *,
        strategy: LockStrategy = LockStrategy.SHARDED,
        shard_count: int = 16,
    ) -> None:
        if shard_count < 1:
            raise ValueError("shard_count 必须 ≥ 1")
        super().__init__(strategy=LockStrategy.RW if strategy is LockStrategy.SHARDED else strategy)
        self._strategy = strategy
        self._seq_lock = threading.Lock()
        self._seq = 0
        self._round_robin = 0
        if strategy is LockStrategy.SHARDED:
            self._global = ReadWriteLock()
            self._shards: list[tuple[threading.RLock, list[tuple[int, ItemT]]]] = [
                (threading.RLock(), []) for _ in range(shard_count)
            ]
            self._data = []
        else:
            self._shards = []
            self._data = []
        self.update(items)

    def _next_seq(self) -> int:
        """分配全局插入序号（独立轻量锁，仅整数自增）。"""
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _copy_data(self) -> list[tuple[int, ItemT]]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return list(self._data)

    def add(self, item: ItemT) -> None:
        """追加元素（保插入序，不去重）。"""
        if self._strategy is LockStrategy.SHARDED:
            with self._seq_lock:
                index = self._round_robin % len(self._shards)
                self._round_robin += 1
            lock, data = self._shards[index]
            with self._global.read(), lock:
                data.append((self._next_seq(), item))
            return
        with self._write_data() as data:
            data.append((self._next_seq(), item))

    def update(self, items: Iterable[ItemT]) -> None:
        """批量追加（保插入序）。"""
        materialized = list(items)
        if self._strategy is LockStrategy.SHARDED:
            for item in materialized:
                self.add(item)
            return
        with self._write_data() as data:
            data.extend((self._next_seq(), item) for item in materialized)

    def discard(self, item: ItemT) -> None:
        """删除首个匹配元素（不存在不报错）。"""
        self._remove(item, missing_ok=True)

    def remove(self, item: ItemT) -> None:
        """删除首个匹配元素（不存在抛 ValueError）。"""
        self._remove(item, missing_ok=False)

    def _remove(self, item: ItemT, *, missing_ok: bool) -> None:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                target = self._find(item)
                if target is None:
                    if missing_ok:
                        return
                    raise ValueError(f"{item!r} not in {type(self).__name__}")
                seq, shard_index = target
                data = self._shards[shard_index][1]
                for position, entry in enumerate(data):
                    if entry[0] == seq:
                        del data[position]
                        break
            return
        with self._write_data() as data:
            for position, entry in enumerate(data):
                if entry[1] == item:
                    del data[position]
                    return
            if not missing_ok:
                raise ValueError(f"{item!r} not in {type(self).__name__}")

    def _find(self, item: ItemT) -> tuple[int, int] | None:
        """全局首个匹配元素的（序号, 段号）；无匹配返回 None（调用方持全局写锁）。"""
        best: tuple[int, int] | None = None
        for shard_index, (_, data) in enumerate(self._shards):
            for seq, value in data:
                if value == item and (best is None or seq < best[0]):
                    best = (seq, shard_index)
        return best

    def clear(self) -> None:
        """清空。"""
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                for _, data in self._shards:
                    data.clear()
            return
        with self._write_data() as data:
            data.clear()

    def _view(self) -> list[tuple[int, ItemT]]:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshots = [list(data) for _, data in self._shards]
            streams = cast("list[Iterable[Any]]", snapshots)
            return list(cast("Iterator[tuple[int, ItemT]]", heapq.merge(*streams)))
        with self._guard.read():
            return list(self._data)

    def to_list(self) -> list[ItemT]:
        """插入序元素列表（快照）。"""
        return [item for _, item in self._view()]

    def _json_data(self) -> object:
        return self.to_list()

    def __contains__(self, item: object) -> bool:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.read():
                for lock, data in self._shards:
                    with lock:
                        if any(value == item for _, value in data):
                            return True
                return False
        with self._guard.read():
            return any(value == item for _, value in self._data)

    def __len__(self) -> int:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                return sum(len(data) for _, data in self._shards)
        with self._guard.read():
            return len(self._data)

    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.to_list())

    @overload
    def __getitem__(self, index: SupportsIndex) -> ItemT: ...

    @overload
    def __getitem__(self, index: slice) -> Self: ...

    def __getitem__(self, index: SupportsIndex | slice) -> ItemT | Self:
        snapshot = self.to_list()
        if isinstance(index, slice):
            return type(self)(snapshot[index])
        return snapshot[index]

    def index(self, value: Any, start: SupportsIndex = 0, stop: SupportsIndex = _MAX_INDEX, /) -> int:
        """元素首次出现的位置（快照内查找）。"""
        return self.to_list().index(value, int(start), int(stop))

    def count(self, value: Any, /) -> int:
        """元素出现次数（快照内统计）。"""
        return self.to_list().count(value)

    def __reversed__(self) -> Iterator[ItemT]:
        return reversed(self.to_list())

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `list` / `tuple` 及同类集合按元素比较。"""
        if isinstance(other, (list, tuple)):
            return self.to_list() == list(cast("Iterable[Any]", other))
        if isinstance(other, (ConcurrentStableList, ConcurrentSortedList)):
            return self.to_list() == list(cast("Iterable[Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentStableSet[ItemT](BaseConcurrent[ItemT, dict[ItemT, int]], Set[ItemT]):
    """并发**插入序**集合：写入保插入序 + 去重、不比较元素；默认分段写（`SHARDED`）。

    业务与契约的唯一集合落点。内部按元素哈希分派段（同元素固定落同段），
    段内 `dict[元素, 序号]` 保插入序，读 / 遍历按整数序号归并还原全局插入序。
    """

    collection_kind: ClassVar[str] = "stable"

    def __init__(
        self,
        items: Iterable[ItemT] = (),
        *,
        strategy: LockStrategy = LockStrategy.SHARDED,
        shard_count: int = 16,
    ) -> None:
        if shard_count < 1:
            raise ValueError("shard_count 必须 ≥ 1")
        super().__init__(strategy=LockStrategy.RW if strategy is LockStrategy.SHARDED else strategy)
        self._strategy = strategy
        self._seq_lock = threading.Lock()
        self._seq = 0
        if strategy is LockStrategy.SHARDED:
            self._global = ReadWriteLock()
            self._shards: list[tuple[threading.RLock, dict[ItemT, int]]] = [
                (threading.RLock(), {}) for _ in range(shard_count)
            ]
            self._data = {}
        else:
            self._shards = []
            self._data = {}
        self.update(items)

    def _next_seq(self) -> int:
        """分配全局插入序号（独立轻量锁，仅整数自增）。"""
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _shard(self, item: ItemT) -> tuple[threading.RLock, dict[ItemT, int]] | None:
        if self._strategy is LockStrategy.SHARDED:
            return self._shards[hash(item) % len(self._shards)]
        return None

    def _copy_data(self) -> dict[ItemT, int]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return dict(self._data)

    def update(self, items: Iterable[ItemT]) -> None:
        """批量插入（去重，保插入序）。"""
        for item in items:
            self.add(item)

    def add(self, item: ItemT) -> None:
        """插入元素（去重；已存在保持原插入位置）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if item not in data:
                    data[item] = self._next_seq()
            return
        with self._write_data() as data:
            if item not in data:
                data[item] = self._next_seq()

    def add_if_absent(self, item: ItemT) -> bool:
        """不存在才插入，返回是否新增（原子）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                if item in data:
                    return False
                data[item] = self._next_seq()
                return True
        with self._write_data() as data:
            if item in data:
                return False
            data[item] = self._next_seq()
            return True

    def discard(self, item: ItemT) -> None:
        """删除元素（不存在不报错）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                data.pop(item, None)
            return
        with self._write_data() as data:
            data.pop(item, None)

    def remove_atomic(self, item: ItemT) -> bool:
        """删除元素并返回是否删除（原子）。"""
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.pop(item, None) is not None
        with self._write_data() as data:
            return data.pop(item, None) is not None

    def clear(self) -> None:
        """清空。"""
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                for _, data in self._shards:
                    data.clear()
            return
        with self._write_data() as data:
            data.clear()

    def _view(self) -> list[ItemT]:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshots = [[(seq, item) for item, seq in data.items()] for _, data in self._shards]
            streams = cast("list[Iterable[Any]]", snapshots)
            merged = cast("Iterator[tuple[int, ItemT]]", heapq.merge(*streams))
            return [item for _, item in merged]
        with self._guard.read():
            return list(self._data)

    def to_list(self) -> list[ItemT]:
        """插入序元素列表（快照）。"""
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

    def __and__(self, other: Set[Any]) -> Self:
        """交集（返回同类，保本实例插入序）。"""
        return type(self)(item for item in self if item in other)

    def __or__(self, other: Set[Any]) -> Self:
        """并集（返回同类，先本实例元素、再 other 新增元素）。"""
        result = type(self)(self)
        for item in other:
            if item not in result:
                result.add(item)
        return result

    def __sub__(self, other: Set[Any]) -> Self:
        """差集（返回同类，保本实例插入序）。"""
        return type(self)(item for item in self if item not in other)

    def __xor__(self, other: Set[Any]) -> Self:
        """对称差集（返回同类，先本实例独有、再 other 独有）。"""
        result = type(self)(item for item in self if item not in other)
        for item in other:
            if item not in self:
                result.add(item)
        return result

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `set` / `frozenset` 及同类集合按元素比较（忽略顺序）。"""
        if isinstance(other, Set):
            return set(self) == set(cast("Set[Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentStableDict[KeyT, ValueT](
    BaseConcurrent[tuple[KeyT, ValueT], dict[KeyT, tuple[int, ValueT]]], Mapping[KeyT, ValueT]
):
    """并发**插入序**字典：写入保插入序、不比较键；默认分段写（`SHARDED`）。

    业务与契约的唯一映射落点。内部按键哈希分派段（同键固定落同段），
    段内 `dict[键, (序号, 值)]` 保插入序，读 / 遍历按整数序号归并还原全局插入序。
    """

    collection_kind: ClassVar[str] = "stable"

    def __init__(
        self,
        items: Mapping[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]] = (),
        *,
        strategy: LockStrategy = LockStrategy.SHARDED,
        shard_count: int = 16,
    ) -> None:
        if shard_count < 1:
            raise ValueError("shard_count 必须 ≥ 1")
        super().__init__(strategy=LockStrategy.RW if strategy is LockStrategy.SHARDED else strategy)
        self._strategy = strategy
        self._seq_lock = threading.Lock()
        self._seq = 0
        if strategy is LockStrategy.SHARDED:
            self._global = ReadWriteLock()
            self._shards: list[tuple[threading.RLock, dict[KeyT, tuple[int, ValueT]]]] = [
                (threading.RLock(), {}) for _ in range(shard_count)
            ]
            self._data = {}
        else:
            self._shards = []
            self._data = {}
        entries: list[tuple[KeyT, ValueT]] = (
            list(cast("Mapping[KeyT, ValueT]", items).items()) if isinstance(items, Mapping) else list(items)
        )
        self.update(entries)

    def _next_seq(self) -> int:
        """分配全局插入序号（独立轻量锁，仅整数自增）。"""
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _shard(self, key: KeyT) -> tuple[threading.RLock, dict[KeyT, tuple[int, ValueT]]] | None:
        if self._strategy is LockStrategy.SHARDED:
            return self._shards[hash(key) % len(self._shards)]
        return None

    def _copy_data(self) -> dict[KeyT, tuple[int, ValueT]]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return dict(self._data)

    def update(self, items: Iterable[tuple[KeyT, ValueT]]) -> None:
        """批量写入（保插入序；同键保持首次插入位置）。"""
        for key, value in items:
            self.set(key, value)

    def set(self, key: KeyT, value: ValueT) -> None:
        """写入键值（已存在的键保持原插入位置）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                existing = data.get(key)
                data[key] = (existing[0] if existing is not None else self._next_seq(), value)
            return
        with self._write_data() as data:
            existing = data.get(key)
            data[key] = (existing[0] if existing is not None else self._next_seq(), value)

    @overload
    def get(self, key: KeyT) -> ValueT | None: ...

    @overload
    def get(self, key: KeyT, default: DefaultT) -> ValueT | DefaultT: ...

    def get(self, key: KeyT, default: Any = None) -> Any:  # pyright: ignore[reportIncompatibleMethodOverride]
        """按键取值（不存在返回 default，默认 None）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data.get(key)
                return entry[1] if entry is not None else default
        with self._guard.read():
            entry = self._data.get(key)
            return entry[1] if entry is not None else default

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
                entry = data.get(key)
                if entry is not None:
                    return entry[1]
                data[key] = (self._next_seq(), value)
                return None
        with self._write_data() as data:
            entry = data.get(key)
            if entry is not None:
                return entry[1]
            data[key] = (self._next_seq(), value)
            return None

    def update_atomic(self, key: KeyT, func: Callable[[ValueT], ValueT]) -> ValueT:
        """原子更新（func 必须纯计算、禁 IO）；键不存在抛 KeyError。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data[key]
                value = func(entry[1])
                data[key] = (entry[0], value)
                return value
        with self._write_data() as data:
            entry = data[key]
            value = func(entry[1])
            data[key] = (entry[0], value)
            return value

    def remove_atomic(self, key: KeyT) -> ValueT:
        """删除并返回旧值（原子）；键不存在抛 KeyError。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.pop(key)[1]
        with self._write_data() as data:
            return data.pop(key)[1]

    def replace_if_equal(self, key: KeyT, expected: ValueT, new: ValueT) -> bool:
        """CAS：当前值等于 expected 才替换（原子）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data.get(key)
                if entry is not None and entry[1] == expected:
                    data[key] = (entry[0], new)
                    return True
                return False
        with self._write_data() as data:
            entry = data.get(key)
            if entry is not None and entry[1] == expected:
                data[key] = (entry[0], new)
                return True
            return False

    def get_and_remove(self, key: KeyT) -> ValueT | None:
        """取走并删除，返回旧值或 None（原子）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data.pop(key, None)
                return entry[1] if entry is not None else None
        with self._write_data() as data:
            entry = data.pop(key, None)
            return entry[1] if entry is not None else None

    @contextmanager
    def get_locked(self, key: KeyT) -> Generator[ValueHolder[ValueT]]:
        """锁内读改写上下文（复杂复合逻辑；holder.value 写回）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data[key]
                holder = ValueHolder(entry[1])
                yield holder
                data[key] = (entry[0], holder.value)
            return
        with self._write_data() as data:
            entry = data[key]
            holder = ValueHolder(entry[1])
            yield holder
            data[key] = (entry[0], holder.value)

    def _view(self) -> list[tuple[KeyT, ValueT]]:
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshots = [[(seq, (key, value)) for key, (seq, value) in data.items()] for _, data in self._shards]
            streams = cast("list[Iterable[Any]]", snapshots)
            merged = cast("Iterator[tuple[int, tuple[KeyT, ValueT]]]", heapq.merge(*streams))
            return [entry for _, entry in merged]
        with self._guard.read():
            return [(key, value) for key, (_, value) in self._data.items()]

    def to_list(self) -> list[tuple[KeyT, ValueT]]:
        """插入序键值对列表（快照）。"""
        return self._view()

    def to_dict(self) -> dict[KeyT, ValueT]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """插入序字典（快照）。"""
        return dict(self._view())

    def _json_data(self) -> object:
        return self.to_dict()

    def __getitem__(self, key: KeyT) -> ValueT:
        """按键取值（不存在抛 KeyError）。"""
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data[key][1]
        with self._guard.read():
            return self._data[key][1]

    def keys(self) -> KeysView[KeyT]:
        """键视图（快照上构建，遍历安全）。"""
        return dict(self._view()).keys()

    def items(self) -> ItemsView[KeyT, ValueT]:
        """键值对视图（快照上构建，遍历安全）。"""
        return dict(self._view()).items()

    def values(self) -> ValuesView[ValueT]:
        """值视图（快照上构建，遍历安全）。"""
        return dict(self._view()).values()

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

    def __iter__(self) -> Iterator[KeyT]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """遍历键（Mapping 协议；键值对遍历走 `to_list()` / `items()`）。"""
        return iter(self.keys())

    def __eq__(self, other: object) -> bool:
        """内容相等：与 `dict` / 映射及同类集合按键值比较（忽略顺序）。"""
        if isinstance(other, Mapping):
            return dict(self._view()) == dict(cast("Mapping[Any, Any]", other))
        return NotImplemented

    __hash__ = BaseObject.__hash__
