"""首页工作台卡片提供者基座契约测试（Kiwi 61）：契约 / 标识 / 常量 / 注册表模板 / 占位空卡片集 / 依赖解析。"""

from collections.abc import Mapping
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from support_app import ApplicationFactory, lifespan

from bms_core.api.deps import get_dashboard_card_registry
from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.exceptions import NotFoundError
from bms_core.dashboard.base import CARD_TYPES, BaseDashboardCardProvider, BaseDashboardCardRegistry
from bms_core.dashboard.null import NullDashboardCardRegistry


class _FakeCard(BaseDashboardCardProvider):
    """测试用卡片提供者。"""

    def __init__(self, key: str) -> None:
        self._key = key

    @property
    def key(self) -> str:
        return self._key

    def describe(self) -> str:
        return f"测试卡片提供者 {self._key}"

    def metadata(self) -> Mapping[str, object]:
        return {"name": self._key, "card_type": "builtin", "render_key": self._key}

    async def fetch(self, params: Mapping[str, object]) -> Mapping[str, object]:
        return {"card": self._key, "arg": params.get("x")}


class _InMemoryRegistry(BaseDashboardCardRegistry):
    """测试用内存注册表：登记 / 解析继承公共实现，验证聚合模板（真实注册表随回补阶段）。"""

    @classmethod
    def _provider_key(cls, provider: BaseDashboardCardProvider) -> str:
        return provider.key


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
    """占位注册表：登记改真实（可解析 / 可枚举）、元数据与取数固定空映射。"""
    registry = NullDashboardCardRegistry()
    card = _FakeCard("todo")
    registry.register(card)
    assert registry.get("todo") is card
    assert registry.keys() == ("todo",)
    assert registry.metadata("todo") == {}
    assert await registry.fetch("todo", {}) == {}


@pytest.mark.kiwi_id(61)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位注册表；路由经 get_dashboard_card_registry 取到同一实例。"""
    app = ApplicationFactory().create(None)
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
