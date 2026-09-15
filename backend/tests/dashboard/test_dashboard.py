"""首页工作台卡片提供者基座契约测试（Kiwi 61）：契约 / 标识 / 常量 / 注册表模板 / 占位空卡片集 / 依赖解析。"""

from collections.abc import Mapping
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_dashboard_card_registry
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.exceptions import NotFoundError
from app.dashboard.base import CARD_TYPES, BaseDashboardCardProvider, BaseDashboardCardRegistry
from app.dashboard.null import NullDashboardCardRegistry
from app.main import create_app, lifespan


class _FakeCard(BaseDashboardCardProvider):
    """测试用卡片提供者。"""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    def metadata(self) -> Mapping[str, object]:
        return {"name": self._key, "card_type": "builtin", "render_key": self._key}

    async def fetch(self, params: Mapping[str, object]) -> Mapping[str, object]:
        return {"card": self._key, "arg": params.get("x")}


class _InMemoryRegistry(BaseDashboardCardRegistry):
    """测试用内存注册表：验证聚合模板（真实注册表随回补阶段）。"""

    def __init__(self) -> None:
        self._providers: dict[str, BaseDashboardCardProvider] = {}

    def register(self, provider: BaseDashboardCardProvider) -> None:
        self._providers[provider.key] = provider

    def get(self, key: str) -> BaseDashboardCardProvider | None:
        return self._providers.get(key)

    def keys(self) -> tuple[str, ...]:
        return tuple(self._providers)


@pytest.mark.kiwi_id(61)
def test_inheritance_and_keys() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseDashboardCardProvider, BaseObject)
    assert issubclass(BaseDashboardCardRegistry, BaseCapability)
    assert issubclass(NullDashboardCardRegistry, BaseDashboardCardRegistry)
    assert issubclass(NullDashboardCardRegistry, BaseNullObject)
    assert BaseDashboardCardRegistry.key == "dashboard_card_registry"

    registry = NullDashboardCardRegistry()
    assert registry.placeholder is True
    assert "占位实现" in registry.describe()


@pytest.mark.kiwi_id(61)
def test_constants() -> None:
    """卡片类型常量（双轨制）。"""
    assert CARD_TYPES == ("builtin", "dataset")


@pytest.mark.kiwi_id(61)
async def test_registry_template_resolution() -> None:
    """聚合模板：注册后解析并委托元数据 / 取数；keys 顺序＝注册顺序；未命中抛 NotFoundError。"""
    registry = _InMemoryRegistry()
    registry.register(_FakeCard("todo"))
    registry.register(_FakeCard("notice"))

    assert registry.keys() == ("todo", "notice")
    assert registry.metadata("todo") == {"name": "todo", "card_type": "builtin", "render_key": "todo"}
    assert await registry.fetch("notice", {"x": 7}) == {"card": "notice", "arg": 7}

    with pytest.raises(NotFoundError):
        registry.metadata("missing")
    with pytest.raises(NotFoundError):
        await registry.fetch("missing", {})


@pytest.mark.kiwi_id(61)
async def test_null_registry_empty_cards() -> None:
    """占位注册表：注册空操作、get None、keys 空、元数据与取数固定空映射。"""
    registry = NullDashboardCardRegistry()
    registry.register(_FakeCard("todo"))
    assert registry.get("todo") is None
    assert registry.keys() == ()
    assert registry.metadata("todo") == {}
    assert await registry.fetch("todo", {}) == {}


@pytest.mark.kiwi_id(61)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位注册表；路由经 get_dashboard_card_registry 取到同一实例。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.dashboard_card_registry, NullDashboardCardRegistry)

        @app.get("/dashboard-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            registry: Annotated[BaseDashboardCardRegistry, Depends(get_dashboard_card_registry)],
        ) -> dict[str, object]:
            data = await registry.fetch("todo", {})
            return {"key": registry.key, "type": type(registry).__name__, "cards": registry.keys(), "data": dict(data)}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/dashboard-probe")

        assert resp.status_code == 200
        assert resp.json() == {
            "key": "dashboard_card_registry",
            "type": "NullDashboardCardRegistry",
            "cards": [],
            "data": {},
        }
