"""数据源统一出口用例（Kiwi 2285，02_09 起 / 02_10 泛化）：路由取数 / 翻译、未命中空结果、批量与缓存。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, BaseGenericDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRecord, DataSourceRegistry
from bms_core.dict.base import DictBatchQuery, DictQuery, DictTranslateQuery
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.outlet import DataSourceOutlet, RoutedDataSource, RoutedDictTranslator


class _FakeProvider(BaseDictDataSource):
    """伪数据源提供者：按给定条目返回。"""

    def __init__(self, data_source: str, items: ConcurrentStableList[DataSourceItem]) -> None:
        self._data_source = data_source
        self._items = items

    @property
    def data_source(self) -> str:
        return self._data_source

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        return self._items


def _registry(records: ConcurrentStableList[DataSourceRecord]) -> DataSourceRegistry:
    return DataSourceRegistry(ConcurrentStableList(records))


_ITEMS: ConcurrentStableList[DataSourceItem] = ConcurrentStableList(
    (
        DataSourceItem(id=1, value="admin", label="管理员", code="admin", parent_id=None, sort=0, status="enabled"),
        DataSourceItem(id=2, value="viewer", label="访客", code="viewer", parent_id=None, sort=1, status="enabled"),
    )
)


def _source(
    records: ConcurrentStableList[DataSourceRecord], providers: ConcurrentStableDict[str, BaseGenericDataSource]
) -> RoutedDataSource:
    return RoutedDataSource(DataSourceOutlet(_registry(records), providers), MemoryDictCacheRegion())


@pytest.mark.kiwi_id(2285)
async def test_by_type_routes_to_provider() -> None:
    """命登记的数据源经 `data_source` 路由到对应提供者（通用条目映射为字典契约条目）。"""
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    source = _source(
        ConcurrentStableList((record,)), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)})
    )
    result = await source.by_type(DictQuery(data_source_key="role"))
    assert result.items is not None and len(result.items) == 2
    assert result.items[0].label == "管理员"


@pytest.mark.kiwi_id(2285)
async def test_unknown_or_disabled_returns_empty() -> None:
    """未登记 / 停用 / 无提供者一律返回空结果（版本 0、items=()）。"""
    disabled = DataSourceRecord(data_source_key="role", name="角色", data_source="platform", status="disabled")
    source = _source(ConcurrentStableList((disabled,)), ConcurrentStableDict({}))
    unknown = await source.by_type(DictQuery(data_source_key="nope"))
    off = await source.by_type(DictQuery(data_source_key="role"))
    assert unknown.version == 0 and unknown.items == ()
    assert off.version == 0 and off.items == ()


@pytest.mark.kiwi_id(2285)
async def test_filters_keyword_and_ids() -> None:
    """关键字 / 按条目 id 子集过滤在出口生效（空子集返回空条目）。"""
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    source = _source(
        ConcurrentStableList((record,)), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)})
    )
    by_keyword = await source.by_type(DictQuery(data_source_key="role", keyword="管理"))
    assert by_keyword.items is not None and len(by_keyword.items) == 1
    by_ids = await source.by_type(DictQuery(data_source_key="role", ids=ConcurrentStableList((2,))))
    assert by_ids.items is not None and by_ids.items[0].id == 2
    empty = await source.by_type(DictQuery(data_source_key="role", ids=ConcurrentStableList(())))
    assert empty.items == ()


@pytest.mark.kiwi_id(2285)
async def test_version_current_returns_none_items() -> None:
    """版本一致时 items 返回 None（省流量）。"""
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    source = _source(
        ConcurrentStableList((record,)), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)})
    )
    current = await source.by_type(DictQuery(data_source_key="role"))
    again = await source.by_type(DictQuery(data_source_key="role", version=current.version))
    assert again.items is None


@pytest.mark.kiwi_id(2285)
async def test_batch_merges() -> None:
    """批量合并逐标识路由，返回内层结果映射。"""
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    source = _source(
        ConcurrentStableList((record,)), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)})
    )
    batch = await source.batch(DictBatchQuery(types=ConcurrentStableList(("role", "nope"))))
    inner = batch.items.get("role")
    assert inner is not None and inner.items is not None
    unknown = batch.items.get("nope")
    assert unknown is not None and unknown.items == ()


@pytest.mark.kiwi_id(2285)
async def test_translate_routes_and_maps() -> None:
    """翻译经路由到提供者，条目 id → label；未命中不占位。"""
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    source = _source(
        ConcurrentStableList((record,)), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)})
    )
    translator = RoutedDictTranslator(source.outlet, MemoryDictCacheRegion())
    mapping = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1, 99))))
    assert mapping.get(1) == "管理员"
    assert mapping.get(99) is None
