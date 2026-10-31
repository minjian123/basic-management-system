"""字典翻译复用缓存（Kiwi 2372）：先读 id 子集缓存、只对缺失 id 回源、回源后回填。

原实现每次 `translate` 都全量 `load`（与「翻译与取数共用同一份 L1」的文档口径不符），表单列表页
几十个 id 的展示会退化成整表搬运；本用例锁死改造后的三条行为。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRecord, DataSourceRegistry
from bms_core.dict.base import DictTranslateQuery
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.outlet import DataSourceOutlet, RoutedDictTranslator


class _CountingProvider(BaseDictDataSource):
    """计次提供者（记录 `load` 次数与最近一次语言）。"""

    def __init__(self, items: ConcurrentStableList[DataSourceItem]) -> None:
        self._items = items
        self.calls = 0
        self.locales: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 固定 `platform`。
        """
        return "platform"

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """取数并计次。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            ConcurrentStableList[DataSourceItem]: 条目。
        """
        self.calls += 1
        self.locales.add(locale)
        return self._items


_ITEMS: ConcurrentStableList[DataSourceItem] = ConcurrentStableList(
    (
        DataSourceItem(id=1, value="admin", label="管理员", code="admin", status="enabled"),
        DataSourceItem(id=2, value="viewer", label="访客", code="viewer", status="enabled"),
    )
)


def _translator(provider: _CountingProvider, cache: MemoryDictCacheRegion) -> RoutedDictTranslator:
    """构造带单条登记的翻译实现。

    Args:
        provider: 提供者。
        cache: 缓存域（与取数共用）。

    Returns:
        RoutedDictTranslator: 翻译实现。
    """
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    outlet = DataSourceOutlet(
        DataSourceRegistry(ConcurrentStableList((record,))),
        ConcurrentStableDict({"platform": provider}),
    )
    return RoutedDictTranslator(outlet, cache)


@pytest.mark.kiwi_id(2372)
async def test_second_translate_hits_cache_without_reload() -> None:
    """同一批 id 第二次翻译不再回源（命中 id 子集缓存）。"""
    provider = _CountingProvider(_ITEMS)
    translator = _translator(provider, MemoryDictCacheRegion())
    first = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1, 2))))
    second = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1, 2))))
    assert dict(first.items()) == {1: "管理员", 2: "访客"}
    assert dict(second.items()) == {1: "管理员", 2: "访客"}
    assert provider.calls == 1


@pytest.mark.kiwi_id(2372)
async def test_partial_hit_only_loads_for_missing_ids() -> None:
    """已缓存的 id 不重复回源，缺失 id 才回源一次并回填。"""
    provider = _CountingProvider(_ITEMS)
    translator = _translator(provider, MemoryDictCacheRegion())
    await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1,))))
    result = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1, 2, 9))))
    assert dict(result.items()) == {1: "管理员", 2: "访客"}
    assert provider.calls == 2


@pytest.mark.kiwi_id(2372)
async def test_unknown_ids_not_in_result() -> None:
    """未命中的 id 不出现在映射中（调用方回退展示原 id）；空 ids 不触发取数。"""
    provider = _CountingProvider(_ITEMS)
    translator = _translator(provider, MemoryDictCacheRegion())
    result = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((9,))))
    assert dict(result.items()) == {}
    empty = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList(())))
    assert dict(empty.items()) == {}
    assert provider.calls == 1


@pytest.mark.kiwi_id(2372)
async def test_locale_passed_to_provider() -> None:
    """翻译按入参 locale 取数（不依赖请求上下文）。"""
    provider = _CountingProvider(_ITEMS)
    translator = _translator(provider, MemoryDictCacheRegion())
    await translator.translate(
        DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1,)), locale="en-US")
    )
    assert list(provider.locales) == ["en-US"]


class _FailingProvider(_CountingProvider):
    """第二次 `load` 抛错（模拟提供者故障）。"""

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """首次正常返回，之后抛错。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            ConcurrentStableList[DataSourceItem]: 首次的条目。

        Raises:
            RuntimeError: 第二次及以后调用。
        """
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("provider down")
        return self._items


@pytest.mark.kiwi_id(2372)
async def test_provider_failure_falls_back_to_cached_subset() -> None:
    """提供者故障时只返回已缓存子集（不抛错、不把故障写进缓存）。"""
    provider = _FailingProvider(_ITEMS)
    translator = _translator(provider, MemoryDictCacheRegion())
    await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1,))))
    result = await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList((1, 2))))
    assert dict(result.items()) == {1: "管理员"}
    assert provider.calls == 2
