"""集合体系唯一继承链测试（Kiwi 2221）。

集合体系**唯一继承链**（所有集合类均（间接）继承基础集合基类 `BaseCollection`，无例外）：

```
BaseCollection（基础集合基类 · 集合体系唯根）
├── BaseSorted（非并发有序）→ SortedList / SortedDict / SortedSet
│   ├── BaseConcurrent（基础并发）→ ConcurrentSorted* / ConcurrentStable*
│   └── BaseAsyncSorted（跨副本异步有序）→ RedisSortedSet / RedisSortedDict
└── BaseCacheSnapshot（通用缓存层）→ RedisSnapshot
```

`BaseSorted` 承载同步读公共段（稳定序列化 / 排序视图 / 分批 / 集合运算）；
`BaseAsyncSorted` 为跨副本形态，**无同步读入口**（同步读公共段显式置为不支持）。
"""

import inspect
from pathlib import Path

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.collections import BaseCollection, BaseSorted
from bms_core.core.concurrent import (
    BaseConcurrent,
    ConcurrentStableDict,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.redis_collections import (
    BaseAsyncSorted,
    BaseCacheSnapshot,
    RedisSnapshot,
    RedisSortedDict,
    RedisSortedSet,
)
from bms_core.core.sorted_collections import (
    ConcurrentSortedDict,
    ConcurrentSortedList,
    ConcurrentSortedSet,
    SortedDict,
    SortedList,
    SortedSet,
)

_ROOT = Path(__file__).resolve().parents[5]
_MANIFEST = _ROOT / "bms文档" / "后端基类清单.md"

LAYERS: tuple[type, ...] = (BaseSorted, BaseConcurrent, BaseAsyncSorted, BaseCacheSnapshot)
"""集合体系除根之外的各层基类。"""

CONCRETE: tuple[type, ...] = (
    SortedList,
    SortedDict,
    SortedSet,
    ConcurrentSortedList,
    ConcurrentSortedSet,
    ConcurrentSortedDict,
    ConcurrentStableList,
    ConcurrentStableSet,
    ConcurrentStableDict,
    RedisSortedSet,
    RedisSortedDict,
    RedisSnapshot,
)
"""集合体系全部具体集合类。"""


@pytest.mark.kiwi_id(2221)
def test_single_root() -> None:
    """唯一根：`BaseCollection` 直继承 `BaseObject`；各层与全部具体类均（间接）继承根（无例外）。"""
    assert issubclass(BaseCollection, BaseObject)
    for layer in LAYERS:
        assert issubclass(layer, BaseCollection)
    for member in CONCRETE:
        assert issubclass(member, BaseCollection)


@pytest.mark.kiwi_id(2221)
def test_branching() -> None:
    """分支关系：有序分支（`BaseSorted`）/ 基础并发（`BaseConcurrent`）/ 跨副本（`BaseAsyncSorted`）
    / 通用缓存（`BaseCacheSnapshot`）。"""
    for member in (SortedList, SortedDict, SortedSet):
        assert issubclass(member, BaseSorted)
        assert not issubclass(member, BaseConcurrent)
    assert issubclass(BaseConcurrent, BaseSorted)
    for member in (ConcurrentSortedList, ConcurrentSortedSet, ConcurrentSortedDict):
        assert issubclass(member, BaseConcurrent)
    for member in (ConcurrentStableList, ConcurrentStableSet, ConcurrentStableDict):
        assert issubclass(member, BaseConcurrent)
        assert member.collection_kind == "stable"
    assert issubclass(BaseAsyncSorted, BaseSorted)
    for member in (RedisSortedSet, RedisSortedDict):
        assert issubclass(member, BaseAsyncSorted)
        assert not issubclass(member, BaseConcurrent)
    assert not issubclass(SortedList, BaseAsyncSorted)
    assert issubclass(BaseCacheSnapshot, BaseCollection)
    assert not issubclass(BaseCacheSnapshot, BaseSorted)
    assert issubclass(RedisSnapshot, BaseCacheSnapshot)
    assert not issubclass(RedisSnapshot, BaseSorted)


@pytest.mark.kiwi_id(2221)
def test_async_has_no_sync_read_entry() -> None:
    """跨副本形态**无同步读入口**：同步读公共段（`to_list` / `__iter__` / `_json_data`）恒抛 `NotImplementedError`。"""
    instance = RedisSortedSet(None, "bms:global:demo:set")  # type: ignore[arg-type]
    assert inspect.iscoroutinefunction(type(instance).size)
    for call in (instance.to_list, lambda: iter(instance), instance._json_data):
        with pytest.raises(NotImplementedError):
            call()


@pytest.mark.kiwi_id(2221)
def test_collection_kind_marks_shape() -> None:
    """形态标记：根 / 有序 / 基础并发 / 跨副本 / 通用缓存 / 插入序各自标识（机器可判形态）。"""
    assert BaseCollection.collection_kind == "collection"
    assert BaseSorted.collection_kind == "sorted"
    assert BaseConcurrent.collection_kind == "sorted_concurrent"
    assert BaseAsyncSorted.collection_kind == "sorted_async"
    assert BaseCacheSnapshot.collection_kind == "cache_snapshot"
    assert SortedList.collection_kind == "sorted"
    assert ConcurrentStableList.collection_kind == "stable"
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
def test_manifest_registers_chain() -> None:
    """清单登记：集合体系唯一链已在《后端基类清单》登记（防止漏登记）。"""
    text = _MANIFEST.read_text(encoding="utf-8")
    for name in ("BaseCollection", "BaseSorted", "BaseConcurrent", "BaseAsyncSorted", "BaseCacheSnapshot"):
        assert name in text
