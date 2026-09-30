"""core 层有序集合实现（**体系内部实现**）：`SortedList` / `SortedDict` / `SortedSet` 与并发升序形态。

**为什么单列一模块（08_02，2026-09-30）**：本模块基于第三方 `sortedcontainers`，**在无依赖环境
（CI `base-integrity` 的 `python:3.14-slim`）不可导入**。集合体系因此按「是否引入该依赖」分层拆分：

- `core/collections.py`：**体系根与有序公共段**（`BaseCollection` / `BaseSorted`）——无依赖；
- `core/concurrent.py`：**基础并发层与插入序形态**（`BaseConcurrent` / `ConcurrentStable*`）——无依赖；
- 本模块：**升序形态**（`Sorted*` / `ConcurrentSorted*`）——依赖止步于此，业务侧导入链保持 stdlib-only。

升序形态为**基座内部实现**（业务与契约不得直接声明 / 继承，排序走排序契约），仅基座内部与用例引用。

继承链（08_05 收链口径）：

- `BaseCollection → BaseSorted → Sorted*`（非并发升序）；
- `BaseSorted → BaseConcurrent` → `ConcurrentSorted*`（并发升序，本模块）
  / `ConcurrentStable*`（并发插入序，见 `core/concurrent.py`）。
"""

import heapq
import threading
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
from typing import Any, Self, SupportsIndex, TypeVar, cast, overload

from sortedcontainers import SortedDict as _SortedDict
from sortedcontainers import SortedList as _SortedList
from sortedcontainers import SortedSet as _SortedSet

from bms_core.core.base import BaseObject
from bms_core.core.collections import MAX_INDEX, BaseSorted
from bms_core.core.concurrent import BaseConcurrent, ConcurrentStableList
from bms_core.core.holder import ValueHolder
from bms_core.core.locking import LockStrategy, ReadWriteLock

DefaultT = TypeVar("DefaultT")
"""`get` 默认值类型（缺省分支返回 `ValueT | DefaultT`）。"""


class SortedList[ItemT](_SortedList[ItemT], BaseSorted[ItemT]):
    """有序列表：按元素（或构造 key=）升序，插入即有序。"""

    def to_list(self) -> list[ItemT]:
        """有序元素列表。

        Returns:
            list[ItemT]: 元素列表。
        """
        return list(self)

    def _json_data(self) -> object:
        """JSON 载荷（数组）。

        Returns:
            object: 元素列表。
        """
        return self.to_list()


class SortedDict[KeyT, ValueT](_SortedDict[KeyT, ValueT], BaseSorted[tuple[KeyT, ValueT]]):
    """有序字典：按键升序，插入即有序。"""

    def to_list(self) -> list[tuple[KeyT, ValueT]]:
        """有序键值对列表。

        Returns:
            list[tuple[KeyT, ValueT]]: 键值对列表。
        """
        return list(self.items())

    def to_dict(self) -> dict[KeyT, ValueT]:  # pyright: ignore[reportIncompatibleMethodOverride]
        """键序字典（内置 dict 副本）。

        Returns:
            dict[KeyT, ValueT]: 键序字典。
        """
        return dict(self.items())

    def merge(self, *others: Iterable[tuple[KeyT, ValueT]]) -> Self:
        """多路归并键值对（同键后者覆盖），返回同类且保持有序。

        Args:
            *others: 其他有序键值对可迭代对象。

        Returns:
            Self: 合并后的同类实例。
        """
        return type(self)(heapq.merge(self.to_list(), *others))

    def keys_intersection(self, other: Iterable[KeyT]) -> Self:
        """按键求交（保留本实例的值），返回同类且保持有序。

        Args:
            other: 参与求交的键集合。

        Returns:
            Self: 交集结果。
        """
        keys = set(other)
        return type(self)((key, self[key]) for key in self if key in keys)

    def keys_union(self, other: Mapping[KeyT, ValueT]) -> Self:
        """按键求并（同键 other 覆盖），返回同类且保持有序。

        Args:
            other: 参与求并的映射。

        Returns:
            Self: 并集结果。
        """
        merged: dict[KeyT, ValueT] = dict(self.items())
        merged.update(other)
        return type(self)(merged)

    def _json_data(self) -> object:
        """JSON 载荷（对象）。

        Returns:
            object: 键序字典。
        """
        return dict(self.items())


class SortedSet[ItemT](_SortedSet[ItemT], BaseSorted[ItemT]):
    """有序集合：按元素升序去重，插入即有序。"""

    def to_list(self) -> list[ItemT]:
        """有序元素列表。

        Returns:
            list[ItemT]: 元素列表。
        """
        return list(self)

    def _json_data(self) -> object:
        """JSON 载荷（数组）。

        Returns:
            object: 元素列表。
        """
        return self.to_list()


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

    def index(self, value: Any, start: SupportsIndex = 0, stop: SupportsIndex = MAX_INDEX, /) -> int:
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
