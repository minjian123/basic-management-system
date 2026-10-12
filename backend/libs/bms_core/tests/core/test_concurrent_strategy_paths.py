"""并发集合非分段（`SNAPSHOT`）策略与复制 / 相等边界用例。

分段（`SHARDED`）为缺省落点、已由既有用例覆盖；本文件补齐 `LockStrategy.SNAPSHOT` 下的写路径
（`_write_data` 写时复制）、`copy.copy` 浅复制、`_json_data` 序列化出口，以及三类集合
`__eq__` 遇非同族对象时的 `NotImplemented` 边界分支。
"""

from __future__ import annotations

import copy
from typing import Any, cast

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
    LockStrategy,
)


def _snapshot_list(*items: object) -> ConcurrentStableList[object]:
    """构造非分段策略列表。

    Args:
        *items: 初始元素。

    Returns:
        ConcurrentStableList[object]: 非分段策略列表。
    """
    return ConcurrentStableList(items, strategy=LockStrategy.SNAPSHOT)


def _snapshot_set(*items: object) -> ConcurrentStableSet[object]:
    """构造非分段策略集合。

    Args:
        *items: 初始元素。

    Returns:
        ConcurrentStableSet[object]: 非分段策略集合。
    """
    return ConcurrentStableSet(items, strategy=LockStrategy.SNAPSHOT)


def _snapshot_dict(*items: tuple[str, object]) -> ConcurrentStableDict[str, object]:
    """构造非分段策略映射。

    Args:
        *items: 初始键值对。

    Returns:
        ConcurrentStableDict[str, object]: 非分段策略映射。
    """
    return ConcurrentStableDict(items, strategy=LockStrategy.SNAPSHOT)


def test_snapshot_list_write_paths() -> None:
    """非分段列表：写入追加、命中删除、未命中 `discard` 与清空。"""
    values = _snapshot_list(1, 2, 3)
    values.add(4)
    assert values.to_list() == [1, 2, 3, 4]
    assert 4 in values

    values.remove(2)
    assert values.to_list() == [1, 3, 4]

    values.discard(99)
    assert values.to_list() == [1, 3, 4]

    values.clear()
    assert values.to_list() == []


def test_snapshot_set_write_paths() -> None:
    """非分段集合：新增 / 条件新增、命中删除、未命中 `discard` 与清空。"""
    values = _snapshot_set(1, 2)
    values.add(3)
    values.add(1)
    assert values.add_if_absent(3) is False
    assert values.add_if_absent(4) is True
    assert values.remove_atomic(2) is True

    values.discard(99)
    assert sorted(cast("Any", values.to_list())) == [1, 3, 4]

    # 并集：`other` 多项且首项已存在 → 循环续行（分支补齐）。
    merged = values | {1, 5, 6}
    assert sorted(cast("Any", merged.to_list())) == [1, 3, 4, 5, 6]

    values.clear()
    assert values.to_list() == []


def test_snapshot_dict_write_paths() -> None:
    """非分段映射：写入 / 条件写入 / 删除 / 成员判定与快照导出。"""
    values = _snapshot_dict(("a", 1))
    values.set("b", 2)
    assert values.put_if_absent("a", 9) == 1
    assert values.put_if_absent("c", 3) is None
    assert "c" in values

    values.delete("a")
    assert values.get("a") is None
    assert values.to_dict() == {"b": 2, "c": 3}


def test_sharded_list_discard_missing_and_remove_hit() -> None:
    """分段列表：未命中 `discard` 静默返回；命中 `remove` 删除后返回。"""
    values = ConcurrentStableList([1, 2])
    values.discard(99)
    values.remove(1)
    assert values.to_list() == [2]


def test_shallow_copy_rebuilds_same_kind() -> None:
    """`copy.copy` 按内容重建同类集合（列表 / 集合 / 映射）。"""
    listed = ConcurrentStableList([1, 2, 3])
    listed_clone = copy.copy(listed)
    assert type(listed_clone) is ConcurrentStableList
    assert listed_clone.to_list() == [1, 2, 3]

    as_set = ConcurrentStableSet([1, 2])
    assert sorted(cast("Any", copy.copy(as_set).to_list())) == [1, 2]

    mapped = ConcurrentStableDict({"a": 1})
    assert copy.copy(mapped).to_dict() == {"a": 1}


def test_json_data_exports_snapshot() -> None:
    """`_json_data`：列表与映射均导出插入序快照。"""
    assert _snapshot_list(1, 2, 3)._json_data() == [1, 2, 3]  # pyright: ignore[reportPrivateUsage]
    assert _snapshot_set("x", "y")._json_data() == ["x", "y"]  # pyright: ignore[reportPrivateUsage]


def test_equality_with_foreign_object_returns_not_implemented() -> None:
    """等同判定遇非同族对象时返回 `NotImplemented`（交由反射比较兜底）。"""
    assert ConcurrentStableList([1]).__eq__(object()) is NotImplemented
    assert ConcurrentStableSet([1]).__eq__(object()) is NotImplemented
    assert ConcurrentStableDict({"a": 1}).__eq__(object()) is NotImplemented
