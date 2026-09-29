"""集合体系收链测试（Kiwi 2221）。

08_05：`BaseSorted` 留作集合体系根（只承载「有序语义 + 稳定序约定」与 `collection_kind` 标记），
其下按接口协议分**同步 / 异步两条平行角色链**——同步链 `BaseSyncSorted`（`Sorted*` 与进程内并发
`ConcurrentSorted*`），异步链 `BaseAsyncSorted`（跨副本 `RedisSortedSet` / `RedisSortedDict`）；
`RedisSnapshot` 为通用缓存快照、非有序集合，保持框架对象体系。同步侧行为零变更，无 sync 与 async 桥接。
"""

import inspect
from pathlib import Path

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.collections import BaseSorted, BaseSyncSorted, SortedDict, SortedList, SortedSet
from bms_core.core.concurrent import (
    BaseConcurrentSorted,
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
)
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.redis_collections import (
    BaseAsyncSorted,
    RedisSnapshot,
    RedisSortedDict,
    RedisSortedSet,
)

_ROOT = Path(__file__).resolve().parents[5]
_MANIFEST = _ROOT / "bms文档" / "后端基类清单.md"


@pytest.mark.kiwi_id(2221)
def test_root_and_two_role_chains() -> None:
    """体系根与两条角色链：同步链挂 `BaseSyncSorted`、异步链挂 `BaseAsyncSorted`，两链互补。"""
    assert issubclass(BaseSorted, BaseObject)
    assert issubclass(BaseSyncSorted, BaseSorted)
    assert issubclass(BaseAsyncSorted, BaseSorted)
    for member in (SortedList, SortedDict, SortedSet, BaseConcurrentSorted):
        assert issubclass(member, BaseSyncSorted)
    for member in (ConcurrentSortedList, ConcurrentSortedSet, ConcurrentSortedDict):
        assert issubclass(member, BaseConcurrentSorted)
    for member in (RedisSortedSet, RedisSortedDict):
        assert issubclass(member, BaseAsyncSorted)
    assert not issubclass(RedisSortedSet, BaseSyncSorted)
    assert not issubclass(SortedList, BaseAsyncSorted)


@pytest.mark.kiwi_id(2221)
def test_redis_snapshot_stays_framework_object() -> None:
    """`RedisSnapshot` 为通用缓存快照、非有序集合 → 保持框架对象体系，不入集合链。"""
    assert issubclass(RedisSnapshot, BaseFrameworkObject)
    assert not issubclass(RedisSnapshot, BaseSorted)


@pytest.mark.kiwi_id(2221)
def test_async_role_layer_common_segment() -> None:
    """异步角色层公共段：`async size()` / `async version()` / `version_key`（属性）为抽象声明且成员实现齐备。"""
    declared = vars(BaseAsyncSorted)
    assert inspect.iscoroutinefunction(declared["size"])
    assert inspect.iscoroutinefunction(declared["version"])
    assert getattr(declared["size"], "__isabstractmethod__", False) is True
    assert getattr(declared["version"], "__isabstractmethod__", False) is True
    version_key = declared["version_key"]
    assert isinstance(version_key, property)
    assert getattr(version_key.fget, "__isabstractmethod__", False) is True
    for member in (RedisSortedSet, RedisSortedDict):
        implemented = vars(member)
        assert inspect.iscoroutinefunction(implemented["size"])
        assert inspect.iscoroutinefunction(implemented["version"])
        assert isinstance(implemented["version_key"], property)


@pytest.mark.kiwi_id(2221)
def test_collection_kind_marks_shape() -> None:
    """形态标记：体系根 / 同步链 / 异步链各自标识（机器可判形态）。"""
    assert BaseSorted.collection_kind == "sorted"
    assert BaseSyncSorted.collection_kind == "sorted_sync"
    assert BaseAsyncSorted.collection_kind == "sorted_async"
    assert SortedList.collection_kind == "sorted_sync"
    assert RedisSortedDict.collection_kind == "sorted_async"


@pytest.mark.kiwi_id(2221)
def test_sync_side_behaviour_unchanged() -> None:
    """行为零变更：同步侧公共段（稳定序列化 / 排序视图 / 分批 / 归并 / 映射与失败分支）仍可用。"""
    items = SortedList([3, 1, 2])
    assert items.to_list() == [1, 2, 3]
    assert items.to_json() == "[1, 2, 3]"
    assert items.sorted_by(lambda value: -value) == [3, 2, 1]
    assert list(items.chunk(2)) == [[1, 2], [3]]
    assert SortedList([1, 3]).merge([2, 4]).to_list() == [1, 2, 3, 4]
    assert SortedDict({"b": 2, "a": 1}).to_dict() == {"a": 1, "b": 2}
    with pytest.raises(TypeError):
        SortedSet([1]).to_dict()
    with pytest.raises(ValueError):
        list(items.chunk(0))


@pytest.mark.kiwi_id(2221)
def test_manifest_registers_two_chains() -> None:
    """清单登记：两条角色链已在《后端基类清单》登记（防止漏登记）。"""
    text = _MANIFEST.read_text(encoding="utf-8")
    assert "BaseSyncSorted" in text
    assert "BaseAsyncSorted" in text
