"""core 层集合体系根与有序公共段：`BaseCollection`（集合体系唯根） + `BaseSorted`（有序公共段）。

**无第三方依赖（集合体系「无依赖面」）**：本模块与 `core/concurrent.py`（基础并发层 + 插入序形态）
只依赖标准库——CI `base-integrity` 的精简镜像（`python:3.14-slim`，不装依赖）会导入基座模块做边界校验，
故根、公共段与插入序形态**不得**引入第三方依赖。升序形态基于第三方 `sortedcontainers`，单列
`bms_core.core.sorted_collections`（依赖止步于该模块）；跨副本与通用缓存形态见 `core/redis_collections.py`。

**集合体系唯一继承链**（所有集合类均（间接）继承基础集合基类 `BaseCollection`，无例外）：

```
BaseCollection（基础集合基类 · 集合体系唯根）
├── BaseSorted（非并发有序：无锁高效）→ SortedList / SortedDict / SortedSet（core/sorted_collections.py）
│   ├── BaseConcurrent（基础并发：锁守卫 + 原子复合操作 + 快照遍历）
│   │   ├── ConcurrentStable*（插入序 · 业务与契约唯一落点；core/concurrent.py）
│   │   └── ConcurrentSorted*（升序 · 体系内部；core/sorted_collections.py）
│   └── BaseAsyncSorted（跨副本异步有序）→ RedisSortedSet / RedisSortedDict
└── BaseCacheSnapshot（通用缓存层）→ RedisSnapshot
```
"""

from __future__ import annotations

import heapq
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from bms_core.core.base import BaseObject
from bms_core.core.serialization import stable_json_dumps

if TYPE_CHECKING:
    from bms_core.core.concurrent import ConcurrentStableDict

MAX_INDEX = 9223372036854775807
"""`Sequence.index` 的默认上界（与内置序列一致；避免用 `None` 与 `SupportsIndex` 冲突）。"""

REPR_ITEM_LIMIT = 10
"""`__str__` / `__repr__` 的默认条目上限（超出截断并在末尾提示总项数）。"""


def render_payload(payload: object) -> str:
    """把 JSON 载荷渲染为「内置字面量」展示文本（超长截断）。

    `_json_data()` 已返回**内置容器**（序列为 `list`、映射为 `dict`），故直接 `repr` 即得
    与内置容器一致的字面量；条目超过 `REPR_ITEM_LIMIT` 时截断，末尾追加「共 N 项」提示。

    Args:
        payload: `_json_data()` 的输出（内置容器）。

    Returns:
        str: 展示文本（不抛错）。
    """
    if isinstance(payload, list):
        items = cast("list[Any]", payload)
        if len(items) <= REPR_ITEM_LIMIT:
            return repr(items)
        head = ", ".join(repr(item) for item in items[:REPR_ITEM_LIMIT])
        return f"[{head}, … 共 {len(items)} 项]"
    if isinstance(payload, dict):
        mapping = cast("dict[Any, Any]", payload)
        if len(mapping) <= REPR_ITEM_LIMIT:
            return repr(mapping)
        head = ", ".join(f"{key!r}: {value!r}" for key, value in list(mapping.items())[:REPR_ITEM_LIMIT])
        return f"{{{head}, … 共 {len(mapping)} 项}}"
    return repr(payload)


class BaseCollection[ItemT](BaseObject, ABC):
    """基础集合基类：集合体系唯根。

    本体系根承载**集合通用语义约定**（不提供可执行公共方法）：集合成员对外输出稳定序
    （**禁止裸无序集合**），有序分**升序 / 插入序**两种形态（`collection_kind` 标记）。
    **所有集合类一律继承本根、无任何例外**——其下按形态分支：

    - `BaseSorted`（非并发有序：无锁、单线程高效）→ `SortedList` / `SortedDict` / `SortedSet`；
      - `BaseConcurrent`（基础并发：锁守卫 + 原子复合操作 + 快照遍历）
        → `ConcurrentSorted*`（升序 · 体系内部）/ `ConcurrentStable*`（插入序 · 业务与契约唯一落点）；
      - `BaseAsyncSorted`（跨副本异步有序：并发由 Lua 原子脚本 + 版本号承载，无同步锁层）
        → `RedisSortedSet` / `RedisSortedDict`；
    - `BaseCacheSnapshot`（通用缓存层：版本号快照 + 惰性重载）→ `RedisSnapshot`。
    """

    collection_kind: ClassVar[str] = "collection"
    """集合形态标识（子层覆写，如 `sorted` / `sorted_concurrent` / `sorted_async` / `stable` / `cache_snapshot`）。"""

    _frozen: bool = False
    """冻结标记：True 时一切写操作抛 `TypeError`（只读快照语义，由 `freeze()` 置位）。"""

    @abstractmethod
    def _freeze_clone(self) -> Self:
        """构造**内容独立**的同类副本（供 `freeze()` 使用；子层按各自形态实现）。

        Returns:
            Self: 同类新实例（内容为当前快照，未置冻结标记）。
        """

    def freeze(self) -> Self:
        """返回**冻结副本**（只读快照）：此后一切写操作抛 `TypeError`。

        用途：把「只读快照」从口头约定落成**真实机制**——写入不再依赖「碰巧没有
        `__setitem__`」这类实现细节。冻结副本内容独立（不受原实例后续写入影响）。

        Returns:
            Self: 冻结副本（内容为当前快照）。
        """
        clone = self._freeze_clone()
        clone._frozen = True
        return clone

    def _ensure_mutable(self) -> None:
        """写操作前置守卫：冻结态直接抛 `TypeError`。

        Raises:
            TypeError: 集合已冻结（只读快照）。
        """
        if self._frozen:
            raise TypeError(f"{type(self).__name__} 为只读快照（已 freeze），禁止写入")

    def __str__(self) -> str:
        """兜底展示：类名 + 形态标记（子层覆写为内容式，跨副本形态覆写为描述式）。

        Returns:
            str: 形如 `RedisSnapshot(<cache_snapshot>)`；**恒不抛错**（不得触发同步读）。
        """
        marker = " 冻结" if self._frozen else ""
        return f"{type(self).__name__}(<{self.collection_kind}{marker}>)"

    def __repr__(self) -> str:
        """字符串输出（与 `__str__` 一致，容器内展示统一）。

        Returns:
            str: 展示文本。
        """
        return self.__str__()


class BaseSorted[ItemT](BaseCollection[ItemT], ABC):
    """有序基类（非并发有序）：稳定序列化、排序视图、分批与集合运算。

    进程内**无锁**有序形态的公共段——`SortedList` / `SortedDict` / `SortedSet` 直接落本层；
    进程内并发形态（`BaseConcurrent` → `ConcurrentSorted*` / `ConcurrentStable*`）亦承本层取得有序公共段，
    在高并发读写外再叠加锁守卫与原子复合操作。
    """

    collection_kind: ClassVar[str] = "sorted"

    def _freeze_clone(self) -> Self:
        """按内容重建同类副本（有序分支统一实现：映射走键值对、序列走元素列表）。

        Returns:
            Self: 同类新实例（未置冻结标记）。
        """
        constructor = cast("Callable[[Iterable[Any]], Self]", type(self))
        payload = self._json_data()
        if isinstance(payload, dict):
            return constructor(cast("dict[Any, Any]", payload).items())
        return constructor(cast("Iterable[Any]", payload))

    @abstractmethod
    def to_list(self) -> list[ItemT]:
        """有序元素列表（内置 list 副本）。

        Returns:
            list[ItemT]: 元素列表。
        """

    @abstractmethod
    def __iter__(self) -> Iterator[ItemT]:
        """遍历（按有序顺序，返回快照安全）。"""

    def to_dict(self) -> ConcurrentStableDict[str, object]:
        """序列类不提供内容映射（避免与根基类字段语义混淆）。

        Raises:
            TypeError: 序列类调用时提示改用 to_list()。
        """
        raise TypeError(f"{type(self).__name__} 不是映射类型，请使用 to_list()")

    def to_json(self, sort_keys: bool = True) -> str:
        """稳定 JSON：序列输出数组、映射输出对象。

        Args:
            sort_keys: 是否按键排序（默认 True，保证输出稳定）。

        Returns:
            str: JSON 字符串。
        """
        return stable_json_dumps(self._json_data(), sort_keys=sort_keys)

    def sorted_by(self, key: Callable[[ItemT], Any], reverse: bool = False) -> list[ItemT]:
        """排序视图：按自定义键返回有序列表副本，不改动自身。

        Args:
            key: 排序键函数。
            reverse: 是否倒序。

        Returns:
            list[ItemT]: 排序后的列表副本。
        """
        return sorted(self, key=key, reverse=reverse)

    def chunk(self, size: int) -> Iterator[list[ItemT]]:
        """分批迭代（每批至多 size 个元素的列表副本）。

        Args:
            size: 每批元素数。

        Yields:
            list[ItemT]: 批次列表。

        Raises:
            ValueError: size < 1。
        """
        if size < 1:
            raise ValueError("chunk size 必须 ≥ 1")
        buffer: list[ItemT] = []
        for item in self:
            buffer.append(item)
            if len(buffer) == size:
                yield buffer
                buffer = []
        if buffer:
            yield buffer

    def merge(self, *others: Iterable[ItemT]) -> Self:
        """多路归并（要求各输入已有序），返回同类且保持有序。

        Args:
            *others: 其他有序可迭代对象。

        Returns:
            Self: 合并后的同类实例。
        """
        streams = cast("list[Iterable[Any]]", [self.to_list(), *others])
        merged = cast("Iterator[ItemT]", heapq.merge(*streams))
        constructor = cast("Callable[[Iterable[ItemT]], Self]", type(self))
        return constructor(merged)

    def __str__(self) -> str:
        """内容式展示：类名 + 内置字面量（超长截断为「共 N 项」）。

        Returns:
            str: 形如 `SortedDict({'a': 1})`（序列为 `[..]`、映射为 `{..}`）。
        """
        marker = " 冻结" if self._frozen else ""
        return f"{type(self).__name__}({render_payload(self._json_data())}{marker})"

    def __repr__(self) -> str:
        """内容式展示（与 `__str__` 一致）。

        Returns:
            str: 展示文本。
        """
        return self.__str__()

    @abstractmethod
    def _json_data(self) -> object:
        """JSON 载荷（序列为数组、映射为对象）。

        Returns:
            object: 可直接 JSON 序列化的载荷。
        """
