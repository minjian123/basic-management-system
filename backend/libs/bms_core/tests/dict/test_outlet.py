"""字典统一出口用例（02_09）：登记路由取数 / 翻译、未命中等价空结果、批量合并。"""

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.base import DictBatchQuery, DictItem, DictQuery, DictTranslateQuery, DictTypeResult
from bms_core.dict.outlet import BaseDictDataProvider, DictOutlet, RoutedDictSource, RoutedDictTranslator
from bms_core.dict.registry import DictRecord, DictRegistry


class _FakeProvider(BaseDictDataProvider):
    """伪数据源提供者：按给定条目返回（版本固定）。"""

    def __init__(self, data_source: str, items: tuple[DictItem, ...], version: int = 3) -> None:
        self._data_source = data_source
        self._items = items
        self._version = version

    @property
    def data_source(self) -> str:
        return self._data_source

    async def fetch(self, query: DictQuery) -> DictTypeResult:
        if query.values is not None:
            subset = tuple(item for item in self._items if item.value in query.values)
            return DictTypeResult(version=self._version, items=subset)
        return DictTypeResult(version=self._version, items=self._items)


def _registry(records: tuple[DictRecord, ...]) -> DictRegistry:
    return DictRegistry(ConcurrentStableList(records))


async def test_by_type_routes_to_provider() -> None:
    """命中登记的字典经 `data_source` 路由到对应提供者。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform.role")
    provider = _FakeProvider("platform.role", (DictItem(id=1, value="admin", label="管理员", code="admin"),))
    outlet = DictOutlet(_registry((record,)), ConcurrentStableDict({"platform.role": provider}))
    result = await RoutedDictSource(outlet).by_type(DictQuery(dict_type="role"))
    assert result.version == 3
    assert result.items is not None and result.items[0].label == "管理员"


async def test_unknown_or_disabled_returns_empty() -> None:
    """未登记 / 停用 / 无提供者一律返回空结果（版本 0、items=()）。"""
    disabled = DictRecord(dict_key="role", name="角色", data_source="platform.role", status="disabled")
    outlet = DictOutlet(_registry((disabled,)), ConcurrentStableDict({}))
    source = RoutedDictSource(outlet)
    unknown = await source.by_type(DictQuery(dict_type="nope"))
    off = await source.by_type(DictQuery(dict_type="role"))
    assert unknown.version == 0 and unknown.items == ()
    assert off.version == 0 and off.items == ()


async def test_batch_merges() -> None:
    """批量合并逐标识路由，返回内层结果映射。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform.role")
    provider = _FakeProvider("platform.role", (DictItem(id=1, value="a", label="A", code="a"),))
    outlet = DictOutlet(_registry((record,)), ConcurrentStableDict({"platform.role": provider}))
    batch = await RoutedDictSource(outlet).batch(DictBatchQuery(types=("role", "nope")))
    assert batch.version == 3
    inner = batch.items.get("role")
    assert inner is not None and inner.version == 3
    unknown = batch.items.get("nope")
    assert unknown is not None and unknown.items == ()


async def test_translate_routes_and_maps() -> None:
    """翻译经路由到提供者，value → label；未命中不占位。"""
    record = DictRecord(dict_key="role", name="角色", data_source="platform.role")
    provider = _FakeProvider("platform.role", (DictItem(id=1, value="a", label="A", code="a"),))
    outlet = DictOutlet(_registry((record,)), ConcurrentStableDict({"platform.role": provider}))
    mapping = await RoutedDictTranslator(outlet).translate(DictTranslateQuery(dict_type="role", values=("a", "z")))
    assert mapping.get("a") == "A"
    assert mapping.get("z") is None
