"""列表偏好协议与查询方案契约测试（Kiwi 781）：协议 / 枚举 / 占位实现 / 依赖解析 / 占位路由。"""

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_query_scheme_store
from app.core.capability import BaseCapability, BaseNullObject
from app.core.config import get_settings
from app.core.plugin import BasePluggable, resolve_plugin
from app.listing.base import (
    LIST_DENSITIES,
    LIST_PREF_KEY_PREFIX,
    BaseQuerySchemeStore,
    ListPreference,
    QueryScheme,
    QuerySchemeScope,
    QuerySchemeTarget,
    build_list_pref_key,
)
from app.listing.null import NullQuerySchemeStore
from app.main import ApplicationFactory, lifespan

API = "/api/v1/query-schemes"


@pytest.fixture(autouse=True)
def force_null_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """占位用例固定 null 实现（避免 dev 环境覆盖为 sql 影响占位断言）。"""
    monkeypatch.setenv("BMS_QUERY_SCHEME_STORE__PROVIDER", "null")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class _InMemorySchemeStore(BaseQuerySchemeStore):
    """测试用内存查询方案存储（验证契约聚合行为；真实存储随通用能力阶段）。"""

    def __init__(self) -> None:
        self._items: dict[int, QueryScheme] = {}
        self._seq = 0

    async def list(self, target: QuerySchemeTarget, *, field_key: str | None = None) -> tuple[QueryScheme, ...]:
        return tuple(
            scheme
            for scheme in self._items.values()
            if scheme.target == target and (field_key is None or scheme.field_key == field_key)
        )

    async def get(self, scheme_id: int) -> QueryScheme | None:
        return self._items.get(scheme_id)

    async def save(self, scheme: QueryScheme) -> QueryScheme:
        stored = scheme.model_copy(deep=True)
        scheme_id = stored.id
        if scheme_id is None:
            self._seq += 1
            scheme_id = self._seq
            stored = stored.model_copy(update={"id": scheme_id})
        self._items[scheme_id] = stored
        return stored

    async def delete(self, scheme_id: int) -> bool:
        return self._items.pop(scheme_id, None) is not None

    async def resolve_default(self, target: QuerySchemeTarget, *, field_key: str | None = None) -> QueryScheme | None:
        defaults = [scheme for scheme in await self.list(target, field_key=field_key) if scheme.is_default]
        return defaults[0] if defaults else None


@pytest.mark.kiwi_id(781)
def test_list_preference_protocol() -> None:
    """列表偏好协议：键 `list.{form_key}` / 密度取值 / 数据结构默认值。"""
    assert LIST_PREF_KEY_PREFIX == "list"
    assert LIST_DENSITIES == ("default", "small")
    assert build_list_pref_key("user_form") == "list.user_form"

    pref = ListPreference()
    assert pref.page_size == 20
    assert pref.density == "default"
    assert pref.columns == []
    assert pref.query == {}


@pytest.mark.kiwi_id(781)
def test_query_scheme_contract() -> None:
    """查询方案契约：继承 / 标识 / 枚举取值 / 数据契约（含 name）。"""
    assert issubclass(BaseQuerySchemeStore, BasePluggable)
    assert issubclass(BaseQuerySchemeStore, BaseCapability)
    assert BaseQuerySchemeStore.key == "query_scheme_store"

    assert {scope.value for scope in QuerySchemeScope} == {"user", "tenant", "platform"}
    assert {target.value for target in QuerySchemeTarget} == {"items", "business"}

    scheme = QueryScheme(name="我的方案", target=QuerySchemeTarget.BUSINESS)
    assert scheme.name == "我的方案"
    assert scheme.scope is QuerySchemeScope.USER
    assert scheme.is_default is False
    assert scheme.shared is False


@pytest.mark.kiwi_id(781)
async def test_null_store_fixed_returns() -> None:
    """占位实现：列表空 / 详情 None / 保存原样 / 删除失败 / 默认解析 None。"""
    store = NullQuerySchemeStore()
    assert issubclass(NullQuerySchemeStore, BaseNullObject)
    assert store.placeholder is True
    assert "占位实现" in store.describe()

    assert await store.list(QuerySchemeTarget.BUSINESS) == ()
    assert await store.get(1) is None

    scheme = QueryScheme(name="x", target=QuerySchemeTarget.ITEMS)
    assert await store.save(scheme) is scheme
    assert await store.delete(1) is False
    assert await store.resolve_default(QuerySchemeTarget.BUSINESS, field_key="user_form") is None


@pytest.mark.kiwi_id(781)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位查询方案存储；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        store = app.state.query_scheme_store
        assert isinstance(store, NullQuerySchemeStore)
        assert resolve_plugin("query_scheme_store", None) is store


@pytest.mark.kiwi_id(781)
async def test_placeholder_routes(client: AsyncClient) -> None:
    """占位路由：列表空 / 默认方案 None / 新建回显 / 删除 data null。"""
    listed = await client.get(API, params={"target": "business"})
    assert listed.status_code == 200
    assert listed.json()["data"] == []

    default = await client.get(f"{API}/default", params={"target": "business", "field_key": "user_form"})
    assert default.status_code == 200
    assert default.json()["data"] is None

    missing = await client.get(f"{API}/1")
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002

    created = await client.post(API, json={"name": "我的方案", "target": "business", "field_key": "user_form"})
    assert created.status_code == 200
    assert created.json()["data"]["name"] == "我的方案"

    updated = await client.put(f"{API}/1", json={"name": "更新方案", "target": "business"})
    assert updated.status_code == 200
    assert updated.json()["data"]["id"] == "1"
    assert updated.json()["data"]["name"] == "更新方案"

    deleted = await client.delete(f"{API}/1")
    assert deleted.status_code == 200
    assert deleted.json()["data"] is None


@pytest.mark.kiwi_id(781)
async def test_routes_with_in_memory_store() -> None:
    """占位路由 + 内存存储：新建 / 列表 / 详情 / 默认解析 / 删除成功路径。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        store = _InMemorySchemeStore()
        app.dependency_overrides[get_query_scheme_store] = lambda: store
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            created = await client.post(API, json={"name": "我的方案", "target": "business", "is_default": True})
            scheme_id = created.json()["data"]["id"]
            assert scheme_id is not None

            listed = await client.get(API, params={"target": "business"})
            assert [scheme["name"] for scheme in listed.json()["data"]] == ["我的方案"]

            detail = await client.get(f"{API}/{scheme_id}")
            assert detail.status_code == 200
            assert detail.json()["data"]["name"] == "我的方案"

            default = await client.get(f"{API}/default", params={"target": "business"})
            assert default.json()["data"]["name"] == "我的方案"

            deleted = await client.delete(f"{API}/{scheme_id}")
            assert deleted.status_code == 200
            assert (await client.get(f"{API}/{scheme_id}")).status_code == 404
