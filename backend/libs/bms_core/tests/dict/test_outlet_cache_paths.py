"""数据源统一出口·缓存与级联路径补齐用例（`02_09` / `02_10` 补齐）。

补齐 `bms_core/dict/outlet.py` 中既有用例未覆盖的路径：

- `EmptyDictDataSource.data_source` 标识；
- `RoutedDataSource.cache` 属性与「缓存已回填 → 二次取数短路」；
- 互斥锁被占：短暂等待后重读缓存并命中；
- 级联过滤（`parent_id=0` 顶层 / 指定上级）；
- `_cache_snapshot` / `_snapshot_payload` 纯函数（非映射、版本不符、条目列非映射）；
- `RoutedDictTranslator`：未登记提供者 → 空映射；入参去重后为空 → 空映射。
"""

from __future__ import annotations

from typing import Any, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseGenericDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRecord, DataSourceRegistry
from bms_core.db.tenant import current_tenant_id_str
from bms_core.dict.base import (
    DEFAULT_LOCALE,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.outlet import (
    DataSourceOutlet,
    EmptyDictDataSource,
    RoutedDataSource,
    RoutedDictTranslator,
    _cache_snapshot,  # pyright: ignore[reportPrivateUsage]
    _snapshot_payload,  # pyright: ignore[reportPrivateUsage]
    build_data_source_outlet,
    register_data_source,
    registered_data_sources,
)

_RECORD = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")

_ITEMS: ConcurrentStableList[DataSourceItem] = ConcurrentStableList(
    (
        DataSourceItem(id=1, value="top", label="顶层", code="top", parent_id=None, sort=0, status="enabled"),
        DataSourceItem(id=2, value="child", label="子级", code="child", parent_id=1, sort=1, status="enabled"),
    )
)


class _Provider(EmptyDictDataSource):
    """提供者替身：按给定条目返回，并记录调用次数。"""

    def __init__(self) -> None:
        """初始化。"""
        super().__init__("platform")
        self.calls = 0

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """记录调用并回条目集。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            tuple[DataSourceItem, ...]: 条目集。
        """
        self.calls += 1
        return _ITEMS


class _OnceEmptyCache(MemoryDictCacheRegion):
    """首读恒未命中的缓存（模拟并发窗口内缓存被他人回填）。"""

    def __init__(self) -> None:
        """初始化。"""
        super().__init__()
        self.reads = 0

    async def aget_type(self, tenant: str | None, locale: str, data_source_key: str) -> object | None:
        """首次读返回 None，其后委托内存实现。

        Args:
            tenant: 租户标识。
            locale: 语言。
            data_source_key: 数据源标识。

        Returns:
            object | None: 缓存值。
        """
        self.reads += 1
        if self.reads == 1:
            return None
        return await super().aget_type(tenant, locale, data_source_key)


def _outlet(provider: BaseGenericDataSource) -> DataSourceOutlet:
    """构造出口（单条启用登记 + 单提供者）。

    Args:
        provider: 数据源提供者。

    Returns:
        DataSourceOutlet: 出口。
    """
    return DataSourceOutlet(
        DataSourceRegistry(ConcurrentStableList([_RECORD])),
        ConcurrentStableDict({"platform": provider}),
    )


def test_empty_dict_data_source_identifier() -> None:
    """占位提供者的数据出口标识。"""
    assert EmptyDictDataSource("platform").data_source == "platform"


async def test_cache_property_and_second_read_short_circuits() -> None:
    """`cache` 属性暴露实例；缓存回填后二次取数短路（不再回源）。"""
    provider = _Provider()
    cache = MemoryDictCacheRegion()
    source = RoutedDataSource(_outlet(cast("Any", provider)), cache)
    assert source.cache is cache
    assert source.outlet is not None

    first = await source.by_type(DictQuery(data_source_key="role"))
    assert [item.value for item in first.items or ()] == ["top", "child"]

    second = await source.by_type(DictQuery(data_source_key="role"))
    assert [item.value for item in second.items or ()] == ["top", "child"]
    assert provider.calls == 1


async def test_lock_contention_rereads_cache_after_wait() -> None:
    """互斥锁被占：等待后重读缓存命中，不再回源。"""
    provider = _Provider()
    cache = _OnceEmptyCache()
    source = RoutedDataSource(_outlet(cast("Any", provider)), cache)
    tenant = current_tenant_id_str()
    await cache.aset_type(
        tenant, DEFAULT_LOCALE, "role", _snapshot_payload(DictTypeResult(version=0, items=ConcurrentStableList(())))
    )
    assert await cache.alock(tenant, DEFAULT_LOCALE, "role", "holder") is True
    cache.reads = 0

    result = await source.by_type(DictQuery(data_source_key="role"))
    assert result.items == ()
    assert provider.calls == 0


async def test_cascade_filter_by_parent_id() -> None:
    """级联过滤：`parent_id=0` 取顶层；指定上级取子级。"""
    source = RoutedDataSource(_outlet(cast("Any", _Provider())), MemoryDictCacheRegion())

    top = await source.by_type(DictQuery(data_source_key="role", parent_id=0))
    assert [item.value for item in top.items or ()] == ["top"]

    children = await source.by_type(DictQuery(data_source_key="role", parent_id=1))
    assert [item.value for item in children.items or ()] == ["child"]


def test_cache_snapshot_helper_branches() -> None:
    """`_cache_snapshot`：非映射 / 版本不符不命中；条目列非映射时退化为空条目集。"""
    payload = _snapshot_payload(DictTypeResult(version=2, items=ConcurrentStableList(()), has_more=False, total=0))
    hit = _cache_snapshot(payload, 2)
    assert hit is not None
    assert hit.items == ()

    assert _cache_snapshot(object(), 2) is None
    assert _cache_snapshot(payload, 3) is None

    broken: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    broken.set("version", 2)
    broken.set("items", "not-a-list")
    fallback = _cache_snapshot(broken, 2)
    assert fallback is not None
    assert fallback.items == ()
    assert fallback.total == 0


async def test_lock_held_with_filtered_query_skips_reread_and_release() -> None:
    """锁被占 + 带过滤条件（不可缓存）：等待后直接回源，且不释放他人锁。"""
    provider = _Provider()
    cache = _OnceEmptyCache()
    source = RoutedDataSource(_outlet(cast("Any", provider)), cache)
    tenant = current_tenant_id_str()
    assert await cache.alock(tenant, DEFAULT_LOCALE, "role", "holder") is True

    result = await source.by_type(DictQuery(data_source_key="role", keyword="顶层"))
    assert [item.value for item in result.items or ()] == ["top"]
    assert provider.calls == 1
    # 他人持有的锁未被释放。
    assert await cache.alock(tenant, DEFAULT_LOCALE, "role", "another") is False


async def test_lock_held_and_stale_cache_falls_through_to_load() -> None:
    """锁被占 + 重读到的缓存版本不符 → 视为未命中，继续回源。"""
    provider = _Provider()
    cache = _OnceEmptyCache()
    source = RoutedDataSource(_outlet(cast("Any", provider)), cache)
    tenant = current_tenant_id_str()
    await cache.aset_type(
        tenant, DEFAULT_LOCALE, "role", _snapshot_payload(DictTypeResult(version=99, items=ConcurrentStableList(())))
    )
    assert await cache.alock(tenant, DEFAULT_LOCALE, "role", "holder") is True
    cache.reads = 0

    result = await source.by_type(DictQuery(data_source_key="role"))
    assert [item.value for item in result.items or ()] == ["top", "child"]
    assert provider.calls == 1


def test_outlet_registry_property() -> None:
    """出口 `registry` 属性暴露登记注册表。"""
    outlet = _outlet(cast("Any", _Provider()))
    assert outlet.registry.get("role") is not None


async def test_empty_provider_load_returns_empty() -> None:
    """占位提供者 `load` 恒返回空元组。"""
    assert await EmptyDictDataSource("platform").load("role", DEFAULT_LOCALE) == ()


def test_provider_registry_and_outlet_build() -> None:
    """提供者注册表与出口装配入口（构建期清单 + 已注入提供者）。"""
    provider = _Provider()
    register_data_source(cast("Any", provider))
    assert registered_data_sources().get("platform") is provider

    built = build_data_source_outlet()
    assert built.registry.get("role") is not None


async def test_translator_missing_provider_and_empty_ids() -> None:
    """翻译：未登记提供者 → 空映射；入参去重后为空 → 空映射。"""
    translator = RoutedDictTranslator(_outlet(cast("Any", _Provider())), MemoryDictCacheRegion())
    # 登记里无 `nope` → 无提供者。
    assert await translator.translate(DictTranslateQuery(data_source_key="nope", ids=ConcurrentStableList((1,)))) == {}
    assert await translator.translate(DictTranslateQuery(data_source_key="role", ids=ConcurrentStableList(()))) == {}
