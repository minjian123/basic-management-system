"""字典统一出口用例（02_09）：登记路由取数 / 翻译、未命中等价空结果、批量合并、缓存与过滤。"""

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.base import DictBatchQuery, DictItem, DictQuery, DictTranslateQuery
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.outlet import BaseDictDataProvider, DictOutlet, RoutedDictSource, RoutedDictTranslator
from bms_core.dict.registry import DictRecord, DictRegistry


class _FakeProvider(BaseDictDataProvider):
    """伪数据源提供者：按给定条目返回。"""

    def __init__(self, data_source: str, items: tuple[DictItem, ...]) -> None:
        self._data_source = data_source
        self._items = items

    @property
    def data_source(self) -> str:
        return self._data_source

    async def load(self, dict_key: str, locale: str) -> tuple[DictItem, ...]:
        return self._items


def _registry(records: tuple[DictRecord, ...]) -> DictRegistry:
    return DictRegistry(ConcurrentStableList(records))


_ITEMS: tuple[DictItem, ...] = (
    DictItem(id=1, value="admin", label="管理员", code="admin", parent_id=None, sort=0, status="enabled"),
    DictItem(id=2, value="viewer", label="访客", code="viewer", parent_id=None, sort=1, status="enabled"),
)


def _source(
    records: tuple[DictRecord, ...], providers: ConcurrentStableDict[str, BaseDictDataProvider]
) -> RoutedDictSource:
    return RoutedDictSource(DictOutlet(_registry(records), providers), MemoryDictCacheRegion())


async def test_by_type_routes_to_provider() -> None:
    """命中登记的字典经 `data_source` 路由到对应提供者。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform")
    source = _source((record,), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)}))
    result = await source.by_type(DictQuery(dict_key="role"))
    assert result.items is not None and len(result.items) == 2
    assert result.items[0].label == "管理员"


async def test_unknown_or_disabled_returns_empty() -> None:
    """未登记 / 停用 / 无提供者一律返回空结果（版本 0、items=()）。"""
    disabled = DictRecord(dict_key="role", name="角色", data_source="platform", status="disabled")
    source = _source((disabled,), ConcurrentStableDict({}))
    unknown = await source.by_type(DictQuery(dict_key="nope"))
    off = await source.by_type(DictQuery(dict_key="role"))
    assert unknown.version == 0 and unknown.items == ()
    assert off.version == 0 and off.items == ()


async def test_filters_keyword_and_values() -> None:
    """关键字 / 按值子集过滤在出口生效。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform")
    source = _source((record,), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)}))
    by_keyword = await source.by_type(DictQuery(dict_key="role", keyword="管理"))
    assert by_keyword.items is not None and len(by_keyword.items) == 1
    by_values = await source.by_type(DictQuery(dict_key="role", values=("viewer",)))
    assert by_values.items is not None and by_values.items[0].value == "viewer"


async def test_version_current_returns_none_items() -> None:
    """版本一致时 items 返回 None（省流量）。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform")
    source = _source((record,), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)}))
    current = await source.by_type(DictQuery(dict_key="role"))
    again = await source.by_type(DictQuery(dict_key="role", version=current.version))
    assert again.items is None


async def test_batch_merges() -> None:
    """批量合并逐标识路由，返回内层结果映射。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform")
    source = _source((record,), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)}))
    batch = await source.batch(DictBatchQuery(types=("role", "nope")))
    inner = batch.items.get("role")
    assert inner is not None and inner.items is not None
    unknown = batch.items.get("nope")
    assert unknown is not None and unknown.items == ()


async def test_translate_routes_and_maps() -> None:
    """翻译经路由到提供者，value → label；未命中不占位。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform")
    source = _source((record,), ConcurrentStableDict({"platform": _FakeProvider("platform", _ITEMS)}))
    translator = RoutedDictTranslator(source.outlet, MemoryDictCacheRegion())
    mapping = await translator.translate(DictTranslateQuery(dict_key="role", values=("admin", "z")))
    assert mapping.get("admin") == "管理员"
    assert mapping.get("z") is None
