"""core 层进程内并发集合：基础并发层（`BaseConcurrent`）与插入序形态（`ConcurrentStable*`）。

- 锁策略与守卫见 bms_core.core.locking（公共横切，可被其它模块复用）
- 遍历一律返回快照副本；跨副本共享见 bms_core.core.redis_collections
- 插入序形态（`ConcurrentStable*`）以**分段写 + 插入序号归并**支持高并发写，是业务与契约的唯一落点
- **无第三方依赖（集合体系「无依赖面」）**：本模块与 `core/collections.py`（根与公共段）只依赖标准库
  ——CI `base-integrity` 的精简镜像（`python:3.14-slim`，不装依赖）会导入基座模块做边界校验；
  升序形态（`ConcurrentSorted*`，基于 `sortedcontainers`）单列 `bms_core.core.sorted_collections`
  （依赖止步于该模块；升序形态为基座内部实现，业务与契约不得直接声明 / 继承）
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
from bms_core.core.collections import MAX_INDEX, BaseSorted
from bms_core.core.holder import ValueHolder
from bms_core.core.locking import LockGuard, LockStrategy, ReadWriteLock

DataT = TypeVar("DataT")
DefaultT = TypeVar("DefaultT")
"""`get` 默认值类型（缺省分支返回 `ValueT | DefaultT`）。"""

MISSING: Any = object()
"""`pop` 的「未给默认值」哨兵：按**身份**比较，区分「缺失」与「值为 None」。

公开名（`sorted_collections` 同口径复用，避免跨模块引用私有符号）；用裸 `object()`
而非自定义类——哨兵不承载任何行为，避免为它引入一个集合体系外的类。
"""


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


class ConcurrentStableList[ItemT](BaseConcurrent[ItemT, list[tuple[int, ItemT]]], Sequence[ItemT]):
    """并发**插入序**列表：写入保插入序、不比较元素；默认分段写（`SHARDED`）。

    业务与契约的唯一列表落点。内部按插入序号（`seq`）分派段，段内已按序号有序，
    读 / 遍历按整数序号归并还原全局插入序。

    **通用功能面（08-4）**：写糖 `append` / `extend` / `+=` / `+` 一律等价于既有原子方法
    （`add` / `update`），不新增写路径；按索引写删 `pop(i)` / `l[i] = v` / `del l[i]` 为
    **O(n)**（先取快照定位序号）；**不提供 `insert` / 原地 `sort` / 原地 `reverse`**
    （须全表重编号并持全局写锁，改用重建集合）。
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
        self._shard_count = shard_count
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

    def _spawn(self, items: Iterable[ItemT]) -> Self:
        """按「同类 + 同策略 + 同段数」构造新实例（切片 / 拼接 / 排序共用，策略保真）。

        Args:
            items: 新实例的初始元素（按给定顺序即插入序）。

        Returns:
            Self: 同类新实例。
        """
        if self._strategy is LockStrategy.SHARDED:
            return type(self)(items, strategy=self._strategy, shard_count=self._shard_count)
        return type(self)(items, strategy=self._strategy)

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
        self._ensure_mutable()
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

    def append(self, item: ItemT) -> None:
        """追加元素（`add` 的同义写法，O(1)）。

        Args:
            item: 待追加元素。
        """
        self._ensure_mutable()
        self.add(item)

    def extend(self, items: Iterable[ItemT]) -> None:
        """批量追加（`update` 的同义写法，O(k)）。

        Args:
            items: 待追加元素序列。
        """
        self._ensure_mutable()
        self.update(items)

    def __iadd__(self, items: Iterable[ItemT]) -> Self:
        """`l += items`：批量追加并返回自身（O(k)）。

        Args:
            items: 待追加元素序列。

        Returns:
            Self: 自身。
        """
        self._ensure_mutable()
        self.update(items)
        return self

    def __add__(self, items: Iterable[ItemT]) -> Self:
        """`l + items`：返回**同类新实例**（原实例不变，策略保真，O(n + k)）。

        Args:
            items: 追加到末尾的元素序列。

        Returns:
            Self: 同类新实例。
        """
        merged = self.to_list()
        merged.extend(items)
        return self._spawn(merged)

    def copy(self) -> Self:
        """浅复制（同类 + 同策略，O(n)）。

        Returns:
            Self: 内容快照构成的新实例。
        """
        return self._spawn(self.to_list())

    def update(self, items: Iterable[ItemT]) -> None:
        """批量追加（保插入序）。"""
        self._ensure_mutable()
        materialized = list(items)
        if self._strategy is LockStrategy.SHARDED:
            for item in materialized:
                self.add(item)
            return
        with self._write_data() as data:
            data.extend((self._next_seq(), item) for item in materialized)

    def discard(self, item: ItemT) -> None:
        """删除首个匹配元素（不存在不报错）。"""
        self._ensure_mutable()
        self._remove(item, missing_ok=True)

    def remove(self, item: ItemT) -> None:
        """删除首个匹配元素（不存在抛 ValueError）。"""
        self._ensure_mutable()
        self._remove(item, missing_ok=False)

    def _remove(self, item: ItemT, *, missing_ok: bool) -> None:
        self._ensure_mutable()
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
        self._ensure_mutable()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                for _, data in self._shards:
                    data.clear()
            return
        with self._write_data() as data:
            data.clear()

    def _delete_seq(self, seq: int) -> bool:
        """按序号删除段内条目（调用方持全局写锁）；返回是否删除。

        Args:
            seq: 插入序号。

        Returns:
            bool: 命中并删除 True。
        """
        for _, data in self._shards:
            for position, entry in enumerate(data):
                if entry[0] == seq:
                    del data[position]
                    return True
        return False

    def _replace_seq(self, seq: int, item: ItemT) -> bool:
        """按序号替换段内条目（调用方持全局写锁，保留原插入位置）；返回是否替换。

        Args:
            seq: 插入序号。
            item: 新元素。

        Returns:
            bool: 命中并替换 True。
        """
        for _, data in self._shards:
            for position, entry in enumerate(data):
                if entry[0] == seq:
                    data[position] = (seq, item)
                    return True
        return False

    def pop(self, index: SupportsIndex = -1) -> ItemT:
        """取走并删除指定位置元素（**O(n)**：先取快照定位序号，再只锁该段删除）。

        Args:
            index: 位置（支持负数；默认末位，与内置 `list.pop` 一致）。

        Returns:
            ItemT: 被取走的元素。

        Raises:
            IndexError: 位置越界 / 空表。
        """
        self._ensure_mutable()
        position = index.__index__()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                seq, item = self._view()[position]
                self._delete_seq(seq)
                return item
        with self._write_data() as data:
            _, item = data[position]
            del data[position]
            return item

    def __setitem__(self, index: SupportsIndex | slice, value: ItemT) -> None:
        """按位置替换元素（**O(n)**；保留原插入位置）。

        Args:
            index: 位置（支持负数）。**切片赋值不支持**（须全表重编号）。
            value: 新元素。

        Raises:
            TypeError: 传入切片（请改用重建集合）。
            IndexError: 位置越界。
        """
        if isinstance(index, slice):
            raise TypeError(f"{type(self).__name__} 不支持切片赋值（须全表重编号），请重建集合")
        self._ensure_mutable()
        position = index.__index__()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                seq, _ = self._view()[position]
                self._replace_seq(seq, value)
            return
        with self._write_data() as data:
            seq, _ = data[position]
            data[position] = (seq, value)

    def __delitem__(self, index: SupportsIndex | slice) -> None:
        """按位置删除元素（**O(n)**）。

        Args:
            index: 位置（支持负数）。**切片删除不支持**（须全表重编号）。

        Raises:
            TypeError: 传入切片（请改用重建集合）。
            IndexError: 位置越界。
        """
        if isinstance(index, slice):
            raise TypeError(f"{type(self).__name__} 不支持切片删除（须全表重编号），请重建集合")
        self._ensure_mutable()
        position = index.__index__()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                seq, _ = self._view()[position]
                self._delete_seq(seq)
            return
        with self._write_data() as data:
            del data[position]

    def sorted(self, key: Callable[[ItemT], Any] | None = None, reverse: bool = False) -> Self:
        """排序结果返回**同类新实例**（O(n log n)；原实例不变）。

        **不提供原地 `sort` / `reverse`**（须全表重编号并持全局写锁，会阻塞所有写）。

        Args:
            key: 排序键函数（缺省按元素本身，要求元素可比较）。
            reverse: 是否倒序。

        Returns:
            Self: 排序后的同类新实例（插入序即排序结果）。
        """
        snapshot = self.to_list()
        if key is None:
            return self._spawn(sorted(cast("list[Any]", snapshot), reverse=reverse))
        return self._spawn(sorted(cast("list[Any]", snapshot), key=key, reverse=reverse))

    def merge(self, *others: Iterable[ItemT]) -> Self:
        """顺序拼接（**插入序不比较元素**，故不做归并），返回同类新实例（O(n + Σk)）。

        Args:
            *others: 追加到末尾的其他可迭代对象。

        Returns:
            Self: 拼接后的同类新实例。
        """
        merged = self.to_list()
        for other in others:
            merged.extend(other)
        return self._spawn(merged)

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
            return self._spawn(snapshot[index])
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
        if isinstance(other, ConcurrentStableList):
            return self.to_list() == list(cast("Iterable[Any]", other))
        # 升序形态（`ConcurrentSortedList`）在 `core/sorted_collections.py`（含依赖模块）——本模块属
        # 「无依赖面」不得反向导入；跨形态比较由对侧 `__eq__` 反射完成，结果不变。
        return NotImplemented

    __hash__ = BaseObject.__hash__


class ConcurrentStableSet[ItemT](BaseConcurrent[ItemT, dict[ItemT, int]], Set[ItemT]):
    """并发**插入序**集合：写入保插入序 + 去重、不比较元素；默认分段写（`SHARDED`）。

    业务与契约的唯一集合落点。内部按元素哈希分派段（同元素固定落同段），
    段内 `dict[元素, 序号]` 保插入序，读 / 遍历按整数序号归并还原全局插入序。

    **通用功能面（08-4）**：`remove` / `pop` / `copy` / `union` / `intersection` /
    `difference` / `symmetric_difference` 及四个 `*_update`——底层复用既有原子
    `add` / `discard` 与运算符，不新增写路径。
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
        self._shard_count = shard_count
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

    def _spawn(self, items: Iterable[ItemT]) -> Self:
        """按「同类 + 同策略 + 同段数」构造新实例（副本 / 集合运算共用）。

        Args:
            items: 新实例的初始元素（按给定顺序即插入序）。

        Returns:
            Self: 同类新实例。
        """
        if self._strategy is LockStrategy.SHARDED:
            return type(self)(items, strategy=self._strategy, shard_count=self._shard_count)
        return type(self)(items, strategy=self._strategy)

    def _copy_data(self) -> dict[ItemT, int]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return dict(self._data)

    def add(self, item: ItemT) -> None:
        """插入元素（去重；已存在保持原插入位置）。"""
        self._ensure_mutable()
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
        self._ensure_mutable()
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
        self._ensure_mutable()
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
        self._ensure_mutable()
        shard = self._shard(item)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.pop(item, None) is not None
        with self._write_data() as data:
            return data.pop(item, None) is not None

    def remove(self, item: ItemT) -> None:
        """删除元素（缺失抛 `KeyError`，与内置 `set.remove` 一致，O(1)）。

        Args:
            item: 待删除元素。

        Raises:
            KeyError: 元素不存在。
        """
        self._ensure_mutable()
        if not self.remove_atomic(item):
            raise KeyError(item)

    def pop(self) -> ItemT:
        """取走并返回**首个插入**元素（O(段数)：全局找最小序号）；空集抛 `KeyError`。

        Returns:
            ItemT: 被取走的元素。

        Raises:
            KeyError: 集合为空。
        """
        self._ensure_mutable()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                target: tuple[int, ItemT] | None = None
                for lock, data in self._shards:
                    with lock:
                        for item, seq in data.items():
                            if target is None or seq < target[0]:
                                target = (seq, item)
                if target is None:
                    raise KeyError(f"{type(self).__name__} 为空")
                _, chosen = target
                for lock, data in self._shards:  # pragma: no branch - 元素必在其哈希段内，首轮必命中
                    with lock:
                        if chosen in data:
                            del data[chosen]
                            break
                return chosen
        with self._write_data() as data:
            if not data:
                raise KeyError(f"{type(self).__name__} 为空")
            chosen = min(data, key=lambda key: data[key])
            del data[chosen]
            return chosen

    def copy(self) -> Self:
        """浅复制（同类 + 同策略，O(n)）。

        Returns:
            Self: 内容快照构成的新实例。
        """
        return self._spawn(self.to_list())

    def union(self, *others: Iterable[ItemT]) -> Self:
        """并集（返回同类，保插入序，O(n + Σk)）。

        Args:
            *others: 参与求并的其他可迭代对象。

        Returns:
            Self: 并集结果。
        """
        result = self.copy()
        for other in others:
            result.update(other)
        return result

    def intersection(self, *others: Iterable[ItemT]) -> Self:
        """交集（返回同类，保本实例插入序，O(n + Σk)）。

        Args:
            *others: 参与求交的其他可迭代对象。

        Returns:
            Self: 交集结果。
        """
        keep = self.to_list()
        for other in others:
            members = set(other)
            keep = [item for item in keep if item in members]
        return self._spawn(keep)

    def difference(self, *others: Iterable[ItemT]) -> Self:
        """差集（返回同类，保本实例插入序，O(n + Σk)）。

        Args:
            *others: 参与求差的其他可迭代对象。

        Returns:
            Self: 差集结果。
        """
        excluded: set[object] = set()
        for other in others:
            excluded.update(other)
        return self._spawn(item for item in self if item not in excluded)

    def symmetric_difference(self, other: Iterable[ItemT]) -> Self:
        """对称差（返回同类，先本实例独有、再 other 独有，O(n + k)）。

        Args:
            other: 参与求对称差的可迭代对象。

        Returns:
            Self: 对称差结果。
        """
        members = set(other)
        only_self = [item for item in self if item not in members]
        only_other = [item for item in members if item not in self]
        return self._spawn([*only_self, *only_other])

    def update(self, *others: Iterable[ItemT]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """原地并集（批量插入，去重，保插入序，O(Σk)）。

        Args:
            *others: 参与并集的其他可迭代对象。
        """
        self._ensure_mutable()
        for other in others:
            for item in other:
                self.add(item)

    def intersection_update(self, *others: Iterable[ItemT]) -> None:
        """原地交集（O(n + Σk)）。

        Args:
            *others: 参与求交的其他可迭代对象。
        """
        self._ensure_mutable()
        keep = set(self.intersection(*others).to_list())
        for item in self.to_list():
            if item not in keep:
                self.discard(item)

    def difference_update(self, *others: Iterable[ItemT]) -> None:
        """原地差集（O(n + Σk)）：删除出现在任一 `others` 中的元素。

        Args:
            *others: 参与求差的其他可迭代对象。
        """
        self._ensure_mutable()
        for other in others:
            for item in other:
                self.discard(item)

    def symmetric_difference_update(self, other: Iterable[ItemT]) -> None:
        """原地对称差（O(n + k)）：本实例独有与 other 独有的并集。

        Args:
            other: 参与求对称差的可迭代对象。
        """
        self._ensure_mutable()
        members = set(other)
        to_remove = [item for item in self.to_list() if item in members]
        to_add = [item for item in members if item not in self]
        for item in to_remove:
            self.discard(item)
        for item in to_add:
            self.add(item)

    def clear(self) -> None:
        """清空。"""
        self._ensure_mutable()
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

    **通用功能面（08-4）**：`d[k] = v` / `del d[k]` / `clear` / `pop` / `popitem` /
    `setdefault` / `fromkeys` / `update(映射 | 键值对 | kwargs)` / `|` / `|=` /
    `sorted_items` / `sorted_keys`——写糖一律等价于既有原子 `set` / `delete`，不新增写路径。
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
        self._shard_count = shard_count
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

    def _spawn(self, items: Mapping[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]]) -> Self:
        """按「同类 + 同策略 + 同段数」构造新实例（副本 / 并集共用）。

        Args:
            items: 新实例的初始键值对（按给定顺序即插入序）。

        Returns:
            Self: 同类新实例。
        """
        if self._strategy is LockStrategy.SHARDED:
            return type(self)(items, strategy=self._strategy, shard_count=self._shard_count)
        return type(self)(items, strategy=self._strategy)

    def _copy_data(self) -> dict[KeyT, tuple[int, ValueT]]:
        """复制内部数据（SNAPSHOT 写时复制）。"""
        return dict(self._data)

    def update(
        self,
        items: Mapping[KeyT, ValueT] | Iterable[tuple[KeyT, ValueT]] = (),
        /,
        **kwargs: ValueT,
    ) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """批量写入：接受**映射 / 键值对可迭代 / 关键字参数**（三者可叠加，O(k)）。

        已存在的键保持原插入位置（与 `set` 同语义）。

        Args:
            items: 映射（走 `.items()`）或键值对可迭代对象。
            **kwargs: 追加写入的键值对（键须为字符串）。
        """
        self._ensure_mutable()
        pairs: Iterable[tuple[KeyT, ValueT]] = (
            cast("Mapping[KeyT, ValueT]", items).items() if isinstance(items, Mapping) else items
        )
        for key, value in pairs:
            self.set(key, value)
        for key, value in kwargs.items():
            self.set(cast("KeyT", key), value)

    def __setitem__(self, key: KeyT, value: ValueT) -> None:
        """`d[key] = value`（等价于 `set`，O(1)）。

        Args:
            key: 键。
            value: 值。
        """
        self._ensure_mutable()
        self.set(key, value)

    def __delitem__(self, key: KeyT) -> None:
        """`del d[key]`（等价于 `delete`；缺失抛 `KeyError`，O(1)）。

        Args:
            key: 键。

        Raises:
            KeyError: 键不存在。
        """
        self._ensure_mutable()
        self.delete(key)

    def clear(self) -> None:
        """清空（O(n)）。"""
        self._ensure_mutable()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                for _, data in self._shards:
                    data.clear()
            return
        with self._write_data() as data:
            data.clear()

    def pop(self, key: KeyT, default: Any = MISSING) -> Any:
        """取走并删除（缺失时返回 `default`，无默认则抛 `KeyError`，O(1)）。

        Args:
            key: 键。
            default: 缺失时的返回值（用哨兵区分「缺失」与「值为 None」）。

        Returns:
            Any: 旧值或 `default`。

        Raises:
            KeyError: 键不存在且未给默认值。
        """
        self._ensure_mutable()
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data.pop(key, None)
                if entry is None:
                    if default is MISSING:
                        raise KeyError(key)
                    return default
                return entry[1]
        with self._write_data() as data:
            entry = data.pop(key, None)
            if entry is None:
                if default is MISSING:
                    raise KeyError(key)
                return default
            return entry[1]

    def popitem(self) -> tuple[KeyT, ValueT]:
        """取走**最后插入**的键值对（LIFO，与内置 `dict` 一致）；空表抛 `KeyError`。

        **O(n)**（先取快照定位末条序号，再只锁该段删除）。

        Returns:
            tuple[KeyT, ValueT]: 被取走的键值对。

        Raises:
            KeyError: 空表。
        """
        self._ensure_mutable()
        if self._strategy is LockStrategy.SHARDED:
            with self._global.write():
                snapshot = self._view()
                if not snapshot:
                    raise KeyError(f"{type(self).__name__} 为空")
                key = snapshot[-1][0]
                entry = self._shards[hash(key) % len(self._shards)][1].pop(key)
                return key, entry[1]
        with self._write_data() as data:
            if not data:
                raise KeyError(f"{type(self).__name__} 为空")
            last_seq = max(seq for seq, _ in data.values())
            for key, (seq, value) in list(data.items()):
                if seq == last_seq:
                    del data[key]
                    return key, value
            raise KeyError(f"{type(self).__name__} 为空")  # pragma: no cover - max() 已保证至少一条命中

    def setdefault(self, key: KeyT, default: ValueT | None = None) -> ValueT | None:
        """存在则返回既有值；不存在则**原子**写入 `default` 并返回它（O(1)）。

        用段锁内「查 → 写」实现（不用 `put_if_absent` 组合：既有值为 `None` 时无法区分）。

        Args:
            key: 键。
            default: 缺失时写入并返回的值。

        Returns:
            ValueT | None: 既有值或 `default`。
        """
        self._ensure_mutable()
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                entry = data.get(key)
                if entry is not None:
                    return entry[1]
                data[key] = (self._next_seq(), cast("ValueT", default))
                return default
        with self._write_data() as data:
            entry = data.get(key)
            if entry is not None:
                return entry[1]
            data[key] = (self._next_seq(), cast("ValueT", default))
            return default

    @classmethod
    def fromkeys(cls, keys: Iterable[KeyT], value: ValueT | None = None) -> Self:
        """由键序列构造同类字典（值统一为 `value`，O(k)）。

        Args:
            keys: 键序列。
            value: 统一值（缺省 `None`）。

        Returns:
            Self: 同类新实例。
        """
        return cls((key, cast("ValueT", value)) for key in keys)

    def copy(self) -> Self:
        """浅复制（同类 + 同策略，O(n)）。

        Returns:
            Self: 内容快照构成的新实例。
        """
        return self._spawn(self._view())

    def __or__(self, other: Mapping[KeyT, ValueT]) -> Self:
        """`d | other`：返回同类新实例（同键 other 覆盖，插入位置不变，O(n + k)）。

        Args:
            other: 参与合并的映射。

        Returns:
            Self: 合并结果。
        """
        merged = self.copy()
        merged.update(other)
        return merged

    def __ior__(self, other: Mapping[KeyT, ValueT]) -> Self:
        """`d |= other`：原地合并并返回自身（O(k)）。

        Args:
            other: 参与合并的映射。

        Returns:
            Self: 自身。
        """
        self._ensure_mutable()
        self.update(other)
        return self

    def sorted_items(
        self,
        key: Callable[[tuple[KeyT, ValueT]], Any] | None = None,
        reverse: bool = False,
    ) -> list[tuple[KeyT, ValueT]]:
        """按键值对排序输出**内置 list**（缺省按键，O(n log n)）。

        Args:
            key: 排序键函数（缺省用键值对首元素即键）。
            reverse: 是否倒序。

        Returns:
            list[tuple[KeyT, ValueT]]: 排序后的键值对列表（内置类型）。
        """
        snapshot = self._view()
        if key is None:
            return sorted(cast("list[Any]", snapshot), key=lambda item: item[0], reverse=reverse)
        return sorted(cast("list[Any]", snapshot), key=key, reverse=reverse)

    def sorted_keys(self, reverse: bool = False) -> list[KeyT]:
        """按键排序输出**内置 list**（O(n log n)）。

        Args:
            reverse: 是否倒序。

        Returns:
            list[KeyT]: 排序后的键列表（内置类型）。
        """
        return sorted(cast("list[Any]", list(self.keys())), reverse=reverse)

    def set(self, key: KeyT, value: ValueT) -> None:
        """写入键值（已存在的键保持原插入位置）。"""
        self._ensure_mutable()
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
        self._ensure_mutable()
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
        self._ensure_mutable()
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
        self._ensure_mutable()
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
        self._ensure_mutable()
        shard = self._shard(key)
        if shard is not None:
            lock, data = shard
            with self._global.read(), lock:
                return data.pop(key)[1]
        with self._write_data() as data:
            return data.pop(key)[1]

    def replace_if_equal(self, key: KeyT, expected: ValueT, new: ValueT) -> bool:
        """CAS：当前值等于 expected 才替换（原子）。"""
        self._ensure_mutable()
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
        self._ensure_mutable()
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
