"""core 层有序集合：BaseCollection + SortedList / SortedDict / SortedSet。

基于 sortedcontainers（插入即有序），统一稳定序列化、排序视图、分批与集合运算；
并发安全版本见 app.core.concurrent，跨副本共享版本见 app.core.redis_collections。
"""

import heapq
import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, Self, cast

from sortedcontainers import SortedDict as _SortedDict
from sortedcontainers import SortedList as _SortedList
from sortedcontainers import SortedSet as _SortedSet

from app.core.base import BaseObject


class BaseCollection[ItemT](BaseObject, ABC):
    """有序集合基类：稳定序列化、排序视图、分批与集合运算。"""

    @abstractmethod
    def to_list(self) -> list[ItemT]:
        """有序元素列表（内置 list 副本）。

        Returns:
            list[ItemT]: 元素列表。
        """

    @abstractmethod
    def __iter__(self) -> Iterator[ItemT]:
        """遍历（按有序顺序，返回快照安全）。"""

    def to_dict(self) -> dict[str, object]:
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
        return json.dumps(self._json_data(), ensure_ascii=False, sort_keys=sort_keys, default=str)

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
        """内容式展示：类名(内容列表)。"""
        return f"{type(self).__name__}({self.to_list()})"

    def __repr__(self) -> str:
        """内容式展示（与 __str__ 一致）。"""
        return self.__str__()

    @abstractmethod
    def _json_data(self) -> object:
        """JSON 载荷（序列为数组、映射为对象）。

        Returns:
            object: 可直接 JSON 序列化的载荷。
        """


class SortedList[ItemT](_SortedList[ItemT], BaseCollection[ItemT]):
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


class SortedDict[KeyT, ValueT](_SortedDict[KeyT, ValueT], BaseCollection[tuple[KeyT, ValueT]]):
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


class SortedSet[ItemT](_SortedSet[ItemT], BaseCollection[ItemT]):
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
