"""字典域缺省实现（Null Object）用例（`02_09` 改指补齐）。

覆盖 `bms_core/dict/null.py`：

- `NullDictSource.by_type`：版本一致短路（`items=None`）、占位两条、按值 / 关键字 / 上级条目过滤、
  `limit` 截断与 `has_more`；
- `NullDictSource.batch`：版本一致各类型返 `None`，否则按类型返回占位结果；
- `NullDictTranslator.translate`：按 value 生成占位标签；
- `NullDictCacheRegion`：读恒未命中、写空操作、删恒 False、版本恒 0（含基类缺省异步实现）。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.base import (
    NULL_DICT_VERSION,
    DictBatchQuery,
    DictQuery,
    DictTranslateQuery,
)
from bms_core.dict.null import (
    NullDictCacheRegion,
    NullDictSource,
    NullDictTranslator,
    _apply_filters,  # pyright: ignore[reportPrivateUsage]
    _placeholder_items,  # pyright: ignore[reportPrivateUsage]
    _type_result,  # pyright: ignore[reportPrivateUsage]
)


async def test_null_source_by_type_placeholder_and_filters() -> None:
    """占位取数：版本一致短路；否则固定两条 + 各维过滤与上限截断。"""
    source = NullDictSource()

    plain = await source.by_type(DictQuery(data_source_key="demo"))
    assert plain.version == NULL_DICT_VERSION
    assert plain.total == 2
    assert plain.has_more is False
    assert [item.value for item in (plain.items or ())] == ["demo-1", "demo-2"]

    same_version = await source.by_type(DictQuery(data_source_key="demo", version=NULL_DICT_VERSION))
    assert same_version.items is None
    assert same_version.total == 0

    limited = await source.by_type(DictQuery(data_source_key="demo", limit=1))
    assert limited.has_more is True
    assert [item.value for item in (limited.items or ())] == ["demo-1"]

    by_values = await source.by_type(DictQuery(data_source_key="demo", values=("demo-2",)))
    assert [item.value for item in (by_values.items or ())] == ["demo-2"]

    by_keyword = await source.by_type(DictQuery(data_source_key="demo", keyword="占位demo2"))
    assert [item.value for item in (by_keyword.items or ())] == ["demo-2"]

    top_level = await source.by_type(DictQuery(data_source_key="demo", parent_id=0))
    assert [item.value for item in (top_level.items or ())] == ["demo-1"]

    children = await source.by_type(DictQuery(data_source_key="demo", parent_id=1))
    assert [item.value for item in (children.items or ())] == ["demo-2"]


async def test_null_source_batch_versions() -> None:
    """批量取数：版本一致各类型返 `None`；否则按类型给占位结果。"""
    source = NullDictSource()

    same_version = await source.batch(DictBatchQuery(types=("a", "b"), version=NULL_DICT_VERSION))
    assert same_version.version == NULL_DICT_VERSION
    assert same_version.items.get("a") is None
    assert same_version.items.get("b") is None

    fresh = await source.batch(DictBatchQuery(types=("a", "b")))
    assert fresh.items.get("a") is not None
    fresh_b = fresh.items.get("b")
    assert fresh_b is not None
    assert len(fresh_b.items or ()) == 2


def test_placeholder_helpers_shape() -> None:
    """占位条目与单类型结果构造（顶层 + 子级各一条）。"""
    items = _placeholder_items("demo")
    assert [item.id for item in items] == [1, 2]
    assert items[0].parent_id is None
    assert items[1].parent_id == 1

    result = _type_result("demo")
    assert result.version == NULL_DICT_VERSION
    assert result.total == 2

    filtered = _apply_filters(items, DictQuery(data_source_key="demo", keyword="demo-1"))
    assert [item.value for item in filtered] == ["demo-1"]


async def test_null_translator_generates_placeholder_labels() -> None:
    """占位翻译：按 value 生成 `占位{类型}:{value}` 标签。"""
    translator = NullDictTranslator()
    result = await translator.translate(DictTranslateQuery(data_source_key="demo", values=("a", "b")))
    assert result.get("a") == "占位demo:a"
    assert result.get("b") == "占位demo:b"


async def test_null_cache_region_is_noop() -> None:
    """占位缓存域：读恒未命中、写空操作、删恒 False、版本恒 0（含基类缺省异步实现）。"""
    region = NullDictCacheRegion()
    assert region.get("k") is None
    region.set("k", "v")
    assert region.delete("k") is False
    assert region.get_global_version() == 0

    await region.aset_type("t1", "zh-CN", "demo", {"version": 1})
    assert await region.aget_type("t1", "zh-CN", "demo") is None
    await region.adrop_type("t1", "zh-CN", "demo")
    assert await region.avalue_subset("t1", "zh-CN", "demo", ConcurrentStableList(["a"])) == {}
    await region.aset_value_subset("t1", "zh-CN", "demo", ConcurrentStableDict())
    assert await region.aversion("t1") == 0
    assert await region.alock("t1", "zh-CN", "demo", "tok") is True
    assert await region.arelease_lock("t1", "zh-CN", "demo", "tok") is True
