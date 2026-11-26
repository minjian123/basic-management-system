"""列表偏好协议与查询方案契约（Kiwi 781）：协议 / 枚举 / 占位实现 / 依赖解析 / 占位路由。

重写口径（13_11）：

- 不再改环境变量切实现（装配常驻后 `Settings` 已固化）：占位语义用**依赖覆盖**注入；
- 依赖解析读装配态应用，断言「本应用登记的提供者 + 实例类型」，不比跨应用实例同一性；
- 路由用例复用会话级 `client`，覆盖一律 `monkeypatch.setitem`。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.api.deps import get_query_scheme_store
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.plugin import BasePluggable
from bms_core.listing.base import (
    LIST_DENSITIES,
    LIST_PREF_KEY_PREFIX,
    BaseQuerySchemeStore,
    ListPreference,
    QueryScheme,
    QuerySchemeScope,
    QuerySchemeTarget,
    build_list_pref_key,
)
from bms_core.listing.null import NullQuerySchemeStore

API = "/api/v1/query-schemes"


class _InMemorySchemeStore(BaseQuerySchemeStore):
    """测试用内存查询方案存储（验证契约聚合行为；真实存储随通用能力阶段）。"""

    def __init__(self) -> None:
        self._items: ConcurrentStableDict[int, QueryScheme] = ConcurrentStableDict()
        self._seq = 0

    async def list(
        self, target: QuerySchemeTarget, *, field_key: str | None = None
    ) -> ConcurrentStableList[QueryScheme]:
        return ConcurrentStableList(
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
        self._items.set(scheme_id, stored)
        return stored

    async def delete(self, scheme_id: int) -> bool:
        return self._items.get_and_remove(scheme_id) is not None

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
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态查询方案存储是契约实现，且装配器记录的提供者与本应用一致。

    插件实例**按应用隔离**（13_11）：进程级 `resolve_plugin` 不带应用时是另一份实例。
    """
    store = service_app.state.query_scheme_store
    assert isinstance(store, BaseQuerySchemeStore)
    assert service_app.state.plugin_providers["query_scheme_store"] in {"sql", "null"}


@pytest.mark.kiwi_id(781)
async def test_placeholder_routes(client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """占位路由：列表空 / 默认方案 None / 新建回显 / 删除 data null。

    占位语义用依赖覆盖注入 `NullQuerySchemeStore`，断言只针对它自己的行为，不假设库为空。
    """
    monkeypatch.setitem(service_app.dependency_overrides, get_query_scheme_store, lambda: NullQuerySchemeStore())
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
async def test_routes_with_in_memory_store(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """占位路由 + 内存存储：新建 / 列表 / 详情 / 默认解析 / 删除成功路径。"""
    store = _InMemorySchemeStore()
    monkeypatch.setitem(service_app.dependency_overrides, get_query_scheme_store, lambda: store)

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
