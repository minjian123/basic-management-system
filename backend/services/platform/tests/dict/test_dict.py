"""字典取数与缓存契约基座测试（Kiwi 844）：三契约 / 常量与数据契约 / 空实现 / 缓存 / 错误码 / 依赖解析 / 占位路由。"""

from collections.abc import Iterator, Mapping
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_dict_cache_region, get_dict_source, get_dict_translator
from bms_core.cache.base import CacheRegion
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.config import get_settings
from bms_core.core.error_codes import ErrorCode
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.dict.base import (
    DICT_CACHE_DOMAIN,
    DICT_PROBE_LIMIT,
    DICT_STATUSES,
    NULL_DICT_VERSION,
    BaseDictSource,
    BaseDictTranslator,
    DictBatchQuery,
    DictBatchResult,
    DictCacheRegion,
    DictItem,
    DictQuery,
    DictTranslateQuery,
    DictTypeResult,
)
from bms_core.dict.null import NullDictCacheRegion, NullDictSource, NullDictTranslator
from bms_platform.main import ApplicationFactory, lifespan

API = "/api/v1/dicts"


@pytest.fixture(autouse=True)
def force_null_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """占位用例固定 null 实现（避免 dev 环境覆盖为 sql / memory 影响占位断言）。"""
    for key in (
        "BMS_DICT_SOURCE__PROVIDER",
        "BMS_DICT_TRANSLATOR__PROVIDER",
        "BMS_DICT_CACHE_REGION__PROVIDER",
    ):
        monkeypatch.setenv(key, "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _InMemoryDictSource(BaseDictSource):
    """测试用内存字典取数（验证参数透传与版本比对；真实取数随字典模块阶段）。"""

    def __init__(self) -> None:
        self.last_query: DictQuery | None = None
        self.last_batch: DictBatchQuery | None = None

    async def by_type(self, query: DictQuery) -> DictTypeResult:
        self.last_query = query
        if query.version == 9:
            return DictTypeResult(version=9, items=None)
        item = DictItem(value=f"{query.dict_type}-x", label=f"内存{query.dict_type}", code="x", color="#000")
        return DictTypeResult(version=9, items=(item,), has_more=False, total=1)

    async def batch(self, query: DictBatchQuery) -> DictBatchResult:
        self.last_batch = query
        if query.version == 9:
            return DictBatchResult(version=9, items={name: None for name in query.types})
        return DictBatchResult(
            version=9,
            items={
                name: DictTypeResult(version=9, items=(DictItem(value=name, label=name),), total=1)
                for name in query.types
            },
        )


class _InMemoryDictTranslator(BaseDictTranslator):
    """测试用内存字典翻译。"""

    async def translate(self, query: DictTranslateQuery) -> Mapping[str, str]:
        return {value: f"{query.locale}:{query.dict_type}:{value}" for value in query.values}


@pytest.mark.kiwi_id(844)
def test_contract_inheritance_and_identity() -> None:
    """三契约继承与能力域标识；缓存域固定 domain；三空实现占位标记。"""
    for contract in (BaseDictSource, BaseDictTranslator, DictCacheRegion):
        assert issubclass(contract, BasePluggable)
        assert issubclass(contract, BaseCapability)
    assert issubclass(DictCacheRegion, CacheRegion)
    assert BaseDictSource.key == BaseDictSource.plugin_key == "dict_source"
    assert BaseDictTranslator.key == BaseDictTranslator.plugin_key == "dict_translator"
    assert DictCacheRegion.key == DictCacheRegion.plugin_key == "dict_cache_region"

    for null_cls in (NullDictSource, NullDictTranslator, NullDictCacheRegion):
        assert issubclass(null_cls, BaseNullObject)

    source = NullDictSource()
    assert source.placeholder is True
    assert "占位实现" in source.describe()
    assert NullDictCacheRegion().domain == DICT_CACHE_DOMAIN == "dict"


@pytest.mark.kiwi_id(844)
def test_constants_and_data_contracts() -> None:
    """常量取值、参数对象与结果契约字段集 / 默认值。"""
    assert DICT_CACHE_DOMAIN == "dict"
    assert DICT_STATUSES == ("enabled", "disabled")
    assert DICT_PROBE_LIMIT == 2001
    assert NULL_DICT_VERSION == 1

    assert set(DictItem.model_fields) == {"value", "label", "code", "parent_id", "sort", "status", "color"}
    assert set(DictQuery.model_fields) == {"dict_type", "version", "keyword", "parent_id", "values", "limit"}
    assert set(DictBatchQuery.model_fields) == {"types", "version", "locale"}
    assert set(DictTranslateQuery.model_fields) == {"dict_type", "values", "locale"}
    assert set(DictTypeResult.model_fields) == {"version", "items", "has_more", "total"}
    assert set(DictBatchResult.model_fields) == {"version", "items"}

    assert DictQuery(dict_type="t").version is None
    assert DictQuery(dict_type="t").values is None
    assert DictBatchQuery(types=("a",)).locale == "zh-CN"
    assert DictTranslateQuery(dict_type="t", values=("a",)).locale == "zh-CN"

    item = DictItem(value="v", label="标签")
    assert item.code == ""
    assert item.parent_id is None
    assert item.sort == 0
    assert item.status == "enabled"
    assert item.color is None

    result = DictTypeResult()
    assert result.items is None
    assert result.has_more is False
    assert result.total == 0


@pytest.mark.kiwi_id(844)
def test_dict_error_codes_registered() -> None:
    """字典错误码 40101~40103 登记且取值正确。"""
    assert ErrorCode.DICT_SOURCE_UNAVAILABLE == 40101
    assert ErrorCode.DICT_TYPE_NOT_FOUND == 40102
    assert ErrorCode.DICT_LOCALE_UNSUPPORTED == 40103


@pytest.mark.kiwi_id(844)
async def test_null_by_type_fixed_version_and_filters() -> None:
    """空实现：固定两条、版本一致 items=None、按值 / 关键字 / 级联 / 上限过滤。"""
    source = NullDictSource()

    result = await source.by_type(DictQuery(dict_type="sys_status"))
    assert result.version == NULL_DICT_VERSION
    assert result.total == 2
    assert result.has_more is False
    assert result.items is not None
    assert [item.value for item in result.items] == ["sys_status-1", "sys_status-2"]
    assert result.items[1].parent_id == "sys_status-1"

    matched = await source.by_type(DictQuery(dict_type="sys_status", version=NULL_DICT_VERSION))
    assert matched.items is None

    subset = await source.by_type(DictQuery(dict_type="t", values=("t-2",)))
    assert subset.items is not None
    assert [item.value for item in subset.items] == ["t-2"]

    empty = await source.by_type(DictQuery(dict_type="t", values=("nope",)))
    assert empty.items == ()

    keyword = await source.by_type(DictQuery(dict_type="t", keyword="占位t2"))
    assert keyword.items is not None and len(keyword.items) == 1

    child = await source.by_type(DictQuery(dict_type="t", parent_id="t-1"))
    assert child.items is not None
    assert [item.value for item in child.items] == ["t-2"]

    limited = await source.by_type(DictQuery(dict_type="t", limit=1))
    assert limited.has_more is True
    assert limited.total == 2
    assert limited.items is not None and len(limited.items) == 1


@pytest.mark.kiwi_id(844)
async def test_null_batch_and_translate() -> None:
    """空实现：批量按类型固定 / 版本一致；翻译按 values 占位。"""
    source = NullDictSource()
    result = await source.batch(DictBatchQuery(types=("a", "b")))
    assert result.version == NULL_DICT_VERSION
    assert set(result.items) == {"a", "b"}
    first = result.items["a"]
    assert first is not None and first.total == 2

    matched = await source.batch(DictBatchQuery(types=("a", "b"), version=NULL_DICT_VERSION))
    assert matched.items == {"a": None, "b": None}

    translated = await NullDictTranslator().translate(DictTranslateQuery(dict_type="t", values=("x", "y")))
    assert translated == {"x": "占位t:x", "y": "占位t:y"}


@pytest.mark.kiwi_id(844)
def test_cache_region_keys_and_version() -> None:
    """缓存域：key 拼接（租户 / 全局）与版本一致性判定。"""
    region = NullDictCacheRegion()
    assert region.domain == "dict"
    assert region.get("k") is None
    region.set("k", {"v": 1}, ttl=30)
    assert region.delete("k") is False
    assert region.get_global_version() == 0
    assert region.dict_key("t1", "zh-CN", "sys_status") == "bms:t1:dict:zh-CN:sys_status"
    assert region.dict_key(None, "en-US", "sys_status") == "bms:global:dict:en-US:sys_status"
    assert region.version_key("t1") == "bms:t1:dict:version"
    assert region.is_version_current(0, tenant="t1") is True
    assert region.is_version_current(1, tenant="t1") is False


@pytest.mark.kiwi_id(844)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配三空实现；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.dict_source, NullDictSource)
        assert isinstance(app.state.dict_translator, NullDictTranslator)
        assert isinstance(app.state.dict_cache_region, NullDictCacheRegion)
        assert resolve_plugin("dict_source", None) is app.state.dict_source
        assert resolve_plugin("dict_translator", None) is app.state.dict_translator
        assert resolve_plugin("dict_cache_region", None) is app.state.dict_cache_region

        request = cast("Request", SimpleNamespace(app=app))
        assert get_dict_source(request) is app.state.dict_source
        assert get_dict_translator(request) is app.state.dict_translator
        assert get_dict_cache_region(request) is app.state.dict_cache_region


@pytest.mark.kiwi_id(844)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：单类型固定 / 版本一致 items null / 按值过滤；批量按类型与版本一致。"""
    single = await client.get(f"{API}/sys_status")
    assert single.status_code == 200
    data = single.json()["data"]
    assert data["version"] == NULL_DICT_VERSION
    assert data["total"] == 2
    assert [item["value"] for item in data["items"]] == ["sys_status-1", "sys_status-2"]

    matched = await client.get(f"{API}/sys_status", params={"version": NULL_DICT_VERSION})
    assert matched.json()["data"]["items"] is None

    subset = await client.get(f"{API}/t", params={"values": "t-1,t-2"})
    assert [item["value"] for item in subset.json()["data"]["items"]] == ["t-1", "t-2"]

    batch = await client.post(f"{API}/batch", json={"types": ["a", "b"]})
    assert batch.status_code == 200
    assert batch.json()["data"]["items"]["a"]["total"] == 2

    batch_matched = await client.post(f"{API}/batch", json={"types": ["a", "b"], "version": NULL_DICT_VERSION})
    assert batch_matched.json()["data"]["items"] == {"a": None, "b": None}


@pytest.mark.kiwi_id(844)
async def test_routes_with_in_memory_implementations() -> None:
    """占位路由 + 内存实现：参数透传 / 版本比对 / 批量。"""
    source = _InMemoryDictSource()
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        app.dependency_overrides[get_dict_source] = lambda: source
        app.dependency_overrides[get_dict_translator] = lambda: _InMemoryDictTranslator()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"{API}/material",
                params={"version": 9, "keyword": "钢", "parent_id": "m-1", "values": "m-1,m-2", "limit": 10},
            )
            assert resp.json()["data"]["items"] is None
            assert source.last_query is not None
            assert source.last_query.dict_type == "material"
            assert source.last_query.version == 9
            assert source.last_query.keyword == "钢"
            assert source.last_query.parent_id == "m-1"
            assert source.last_query.values == ("m-1", "m-2")
            assert source.last_query.limit == 10

            batch = await client.post(f"{API}/batch", json={"types": ["a", "b"], "locale": "en-US"})
            assert batch.json()["data"]["version"] == 9
            assert set(batch.json()["data"]["items"]) == {"a", "b"}
            assert source.last_batch is not None
            assert source.last_batch.locale == "en-US"
