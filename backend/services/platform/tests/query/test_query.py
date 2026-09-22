"""数据查询提供者基座契约测试（Kiwi 55）：契约 / 标识 / 结果契约 / 占位空结果 / 注册表模板 / 依赖解析。"""

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import get_query_provider_registry
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.config import get_settings
from bms_core.core.exceptions import NotFoundError
from bms_core.query.base import BaseQueryProvider, BaseQueryProviderRegistry, QueryResult
from bms_core.query.null import NullQueryProvider, NullQueryProviderRegistry
from bms_platform.main import ApplicationFactory, lifespan


@pytest.fixture(autouse=True)
def force_null_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """占位用例固定 null 实现（避免 dev 环境覆盖为 local 影响占位断言）。"""
    monkeypatch.setenv("BMS_QUERY_PROVIDER_REGISTRY__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _FakeProvider(BaseQueryProvider):
    """测试用查询提供者。"""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    def describe(self) -> str:
        return f"测试查询提供者 {self._key}"

    async def query(self, params: Mapping[str, object]) -> QueryResult:
        return QueryResult(rows=({"provider": self._key, "arg": params.get("x")},), total=1)


class _InMemoryRegistry(BaseQueryProviderRegistry):
    """测试用内存注册表：登记 / 解析继承公共实现，验证聚合模板（真实注册表随回补阶段）。"""

    @classmethod
    def _provider_key(cls, provider: BaseQueryProvider) -> str:
        return provider.key


@pytest.mark.kiwi_id(55)
def test_inheritance_and_keys() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BaseQueryProvider, BaseObject)
    assert issubclass(NullQueryProvider, BaseQueryProvider)
    assert issubclass(NullQueryProvider, BaseNullObject)

    assert issubclass(BaseQueryProviderRegistry, BaseCapability)
    assert issubclass(NullQueryProviderRegistry, BaseQueryProviderRegistry)
    assert issubclass(NullQueryProviderRegistry, BaseNullObject)
    assert BaseQueryProviderRegistry.key == "query_provider_registry"

    registry = NullQueryProviderRegistry()
    assert registry.placeholder is True
    assert "占位实现" in registry.describe()
    assert NullQueryProvider().key == "null_query_provider"
    assert "null_query_provider" in NullQueryProvider().describe()


@pytest.mark.kiwi_id(55)
def test_query_result_defaults_and_frozen() -> None:
    """`QueryResult` 默认值与不可变。"""
    result = QueryResult(rows=())
    assert result.total == 0

    field = "total"
    with pytest.raises(FrozenInstanceError):
        setattr(result, field, 1)


@pytest.mark.kiwi_id(55)
async def test_null_query_provider_empty() -> None:
    """占位提供者恒定返回空结果。"""
    result = await NullQueryProvider().query({"x": 1})
    assert result == QueryResult(rows=(), total=0)


@pytest.mark.kiwi_id(55)
async def test_null_registry_fixed() -> None:
    """占位注册表：登记改真实（可解析 / 可枚举）、query 固定空结果（不抛）。"""
    registry = NullQueryProviderRegistry()
    provider = _FakeProvider("p1")
    registry.register(provider)
    assert registry.get("p1") is provider
    assert registry.keys() == ("p1",)
    assert await registry.query("p1", {}) == QueryResult(rows=(), total=0)


@pytest.mark.kiwi_id(55)
async def test_registry_template_resolution() -> None:
    """聚合模板：注册后按 key 解析并委托；keys 顺序＝注册顺序；未命中抛 NotFoundError。"""
    registry = _InMemoryRegistry()
    registry.register(_FakeProvider("p1"))
    registry.register(_FakeProvider("p2"))

    assert registry.keys() == ("p1", "p2")
    result = await registry.query("p2", {"x": 7})
    assert result == QueryResult(rows=({"provider": "p2", "arg": 7},), total=1)

    with pytest.raises(NotFoundError):
        await registry.query("missing", {})


@pytest.mark.kiwi_id(55)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位注册表；路由经 get_query_provider_registry 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.query_provider_registry, NullQueryProviderRegistry)

        @app.get("/query-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            registry: Annotated[BaseQueryProviderRegistry, Depends(get_query_provider_registry)],
        ) -> dict[str, object]:
            result = await registry.query("any", {})
            return {"key": registry.key, "type": type(registry).__name__, "total": result.total}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/query-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "query_provider_registry", "type": "NullQueryProviderRegistry", "total": 0}
