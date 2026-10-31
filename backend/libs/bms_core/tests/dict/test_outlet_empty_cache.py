"""字典出口缓存边界（Kiwi 2372）：空结果短 TTL / 过滤查询不写缓存 / 提供者异常兜底。

对应详细设计 §4.2「改造点」与 §5「失败分支」：空快照走 `empty_ttl_seconds`、带过滤条件的取数不缓存、
单个 key 的 `load` 抛错只降级为空结果且**不写缓存**（避免把故障固化一个 TTL）。
"""

import json
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.datasource.base import BaseDictDataSource, BaseGenericDataSource, DataSourceItem
from bms_core.datasource.registry import DataSourceRecord, DataSourceRegistry
from bms_core.dict.base import DictOptions, DictQuery
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.outlet import DataSourceOutlet, RoutedDataSource


class _RecordingCache(MemoryDictCacheRegion):
    """记录写入 TTL 的内存缓存域（断言空结果与有数据用不同 TTL）。"""

    def __init__(self) -> None:
        super().__init__()
        self.ttl_calls: ConcurrentStableList[tuple[str, int | None]] = ConcurrentStableList()
        self.payloads: ConcurrentStableList[object] = ConcurrentStableList()

    async def aset_type(
        self,
        tenant: str | None,
        locale: str,
        data_source_key: str,
        value: object,
        ttl: int | None = None,
    ) -> None:
        """记录后委托基类写入。

        Args:
            tenant: 租户标识。
            locale: 语言。
            data_source_key: 字典类型码。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        self.ttl_calls.add((data_source_key, ttl))
        self.payloads.add(value)
        await super().aset_type(tenant, locale, data_source_key, value, ttl)


class _Provider(BaseDictDataSource):
    """按给定行返回的提供者（可选抛错 / 计次）。"""

    def __init__(self, items: ConcurrentStableList[DataSourceItem], *, raises: bool = False) -> None:
        self._items = items
        self._raises = raises
        self.calls = 0

    @property
    def data_source(self) -> str:
        """数据出口标识。

        Returns:
            str: 固定 `platform`。
        """
        return "platform"

    async def load(self, data_source_key: str, locale: str) -> ConcurrentStableList[DataSourceItem]:
        """取数（可抛错）。

        Args:
            data_source_key: 数据源标识。
            locale: 语言。

        Returns:
            ConcurrentStableList[DataSourceItem]: 条目。

        Raises:
            RuntimeError: 构造时 `raises=True`。
        """
        self.calls += 1
        if self._raises:
            raise RuntimeError("table missing")
        return self._items


def _source(
    provider: BaseGenericDataSource, cache: _RecordingCache, options: DictOptions | None = None
) -> RoutedDataSource:
    """构造带单条登记的出口。

    Args:
        provider: 提供者。
        cache: 记录型缓存域。
        options: 出口参数（缺省取配置缺省）。

    Returns:
        RoutedDataSource: 出口实例。
    """
    record = DataSourceRecord(data_source_key="role", name="角色", data_source="platform")
    outlet = DataSourceOutlet(
        DataSourceRegistry(ConcurrentStableList((record,))),
        ConcurrentStableDict({"platform": provider}),
    )
    return RoutedDataSource(outlet, cache, options)


_ITEMS: ConcurrentStableList[DataSourceItem] = ConcurrentStableList(
    (DataSourceItem(id=1, value="admin", label="管理员", code="admin", sort=0, status="enabled"),)
)


@pytest.mark.kiwi_id(2372)
async def test_empty_result_uses_short_ttl() -> None:
    """空结果按 `empty_ttl_seconds` 缓存（有数据按 `type_ttl_seconds`）。"""
    cache = _RecordingCache()
    options = DictOptions(type_ttl_seconds=300, empty_ttl_seconds=7)
    source = _source(_Provider(ConcurrentStableList(())), cache, options)
    result = await source.by_type(DictQuery(data_source_key="role"))
    assert result.items is not None and len(result.items) == 0
    assert cache.ttl_calls[0] == ("role", 7)


@pytest.mark.kiwi_id(2372)
async def test_non_empty_result_uses_type_ttl() -> None:
    """有数据的条目集按 `type_ttl_seconds` 缓存。"""
    cache = _RecordingCache()
    options = DictOptions(type_ttl_seconds=120, empty_ttl_seconds=7)
    source = _source(_Provider(_ITEMS), cache, options)
    await source.by_type(DictQuery(data_source_key="role"))
    assert cache.ttl_calls[0] == ("role", 120)


@pytest.mark.kiwi_id(2372)
async def test_filtered_query_not_cached() -> None:
    """带过滤条件（keyword / ids / parent / limit）的取数不写缓存。"""
    cache = _RecordingCache()
    source = _source(_Provider(_ITEMS), cache)
    await source.by_type(DictQuery(data_source_key="role", keyword="adm"))
    assert len(cache.ttl_calls) == 0


@pytest.mark.kiwi_id(2372)
async def test_provider_error_returns_empty_and_skips_cache() -> None:
    """提供者抛错 → 空结果（版本 0）、不写缓存、异常不外抛（单个字典失败不拖垮页面）。"""
    cache = _RecordingCache()
    provider = _Provider(_ITEMS, raises=True)
    source = _source(provider, cache)
    result = await source.by_type(DictQuery(data_source_key="role"))
    assert result.version == 0
    assert result.items is not None and len(result.items) == 0
    assert len(cache.ttl_calls) == 0
    assert provider.calls == 1


@pytest.mark.kiwi_id(2372)
async def test_cache_payload_is_json_roundtrippable() -> None:
    """缓存载荷必须能 JSON 往返（共享层 `json.dumps` / `json.loads` 口径）。

    回归点：载荷曾用 `ConcurrentStableDict` → `json.dumps(default=str)` 变成 repr 字符串，
    读回 `json.loads` 失败 → Redis 共享层只写不读、跨实例永远打不中（真 Redis 集成用例发现）。
    """
    cache = _RecordingCache()
    source = _source(_Provider(_ITEMS), cache)
    await source.by_type(DictQuery(data_source_key="role"))
    payload = cache.payloads[0]
    restored = cast("dict[str, object]", json.loads(json.dumps(payload, ensure_ascii=False)))
    assert isinstance(restored, dict)
    assert restored["version"] == 0
    assert restored["total"] == 1
    items = cast("list[dict[str, str]]", restored["items"])
    assert [item["label"] for item in items] == ["管理员"]
