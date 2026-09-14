"""数据查询提供者基座契约测试（Kiwi 55）：契约 / 标识 / 结果契约 / 占位空结果 / 注册表模板 / 依赖解析。"""

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_query_provider_registry
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import NotFoundError
from app.main import create_app
from app.query.base import (
    BaseQueryProvider,
    BaseQueryProviderRegistry,
    NullQueryProvider,
    NullQueryProviderRegistry,
    QueryResult,
)


class _FakeProvider(BaseQueryProvider):
    """测试用查询提供者。"""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    async def query(self, params: Mapping[str, object]) -> QueryResult:
        return QueryResult(rows=({"provider": self._key, "arg": params.get("x")},), total=1)


class _InMemoryRegistry(BaseQueryProviderRegistry):
    """测试用内存注册表：验证聚合模板（真实注册表随回补阶段）。"""

    def __init__(self) -> None:
        self._providers: dict[str, BaseQueryProvider] = {}

    def register(self, provider: BaseQueryProvider) -> None:
        self._providers[provider.key] = provider

    def get(self, key: str) -> BaseQueryProvider | None:
        return self._providers.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._providers)


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
    """占位注册表：注册空操作、get None、keys 空、query 固定空结果（不抛）。"""
    registry = NullQueryProviderRegistry()
    registry.register(_FakeProvider("p1"))
    assert registry.get("p1") is None
    assert registry.keys() == ()
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
    app = create_app()
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
