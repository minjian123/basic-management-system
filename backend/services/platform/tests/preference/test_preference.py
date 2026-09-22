"""用户偏好基座契约测试（Kiwi 780）：契约 / 常量 / 键规范 / 占位回退 / 依赖解析 / 占位路由。"""

import pytest
from httpx import AsyncClient

from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.preference.base import (
    PREF_KEY_MAX_LENGTH,
    PREF_KEY_SEPARATOR,
    PREF_MAX_KEYS,
    PREF_VALUE_MAX_BYTES,
    BasePreferenceStore,
    domain_of,
    is_valid_pref_key,
)
from bms_core.preference.null import NullPreferenceStore
from bms_platform.main import ApplicationFactory, lifespan

API = "/api/v1/preferences"


@pytest.mark.kiwi_id(780)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BasePreferenceStore, BasePluggable)
    assert issubclass(BasePreferenceStore, BaseCapability)
    assert issubclass(NullPreferenceStore, BasePreferenceStore)
    assert issubclass(NullPreferenceStore, BaseNullObject)
    assert BasePreferenceStore.key == "preference"
    assert BasePreferenceStore.plugin_key == "preference"

    store = NullPreferenceStore()
    assert store.placeholder is True
    assert "占位实现" in store.describe()


@pytest.mark.kiwi_id(780)
def test_constants() -> None:
    """键规范与单键上限常量。"""
    assert PREF_KEY_SEPARATOR == "."
    assert PREF_KEY_MAX_LENGTH == 128
    assert PREF_VALUE_MAX_BYTES == 65536
    assert PREF_MAX_KEYS == 200


@pytest.mark.kiwi_id(780)
def test_key_validation_and_domain() -> None:
    """键规范校验与域名提取。"""
    for key in ("ui.theme", "list.user_form", "notify.channels", "dashboard.layout"):
        assert is_valid_pref_key(key) is True

    for key in ("", "ui", "Ui.theme", "ui.", ".theme", "ui..theme", "ui.Theme", "a" * 200):
        assert is_valid_pref_key(key) is False

    assert domain_of("list.user_form") == "list"
    assert domain_of("ui.theme") == "ui"
    assert domain_of("nodot") == "nodot"


@pytest.mark.kiwi_id(780)
async def test_null_store_falls_back_to_default() -> None:
    """占位实现固定回退默认值、写 / 重置空操作。"""
    store = NullPreferenceStore()
    assert await store.get("ui.theme") is None
    assert await store.get("ui.theme", default={"mode": "dark"}) == {"mode": "dark"}

    await store.set("ui.theme", {"mode": "dark"})
    assert await store.get("ui.theme", default="fallback") == "fallback"
    assert await store.reset("ui.theme") is False


@pytest.mark.kiwi_id(780)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位偏好存储；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        store = app.state.preference_store
        assert isinstance(store, NullPreferenceStore)
        assert resolve_plugin("preference", None) is store


@pytest.mark.kiwi_id(780)
async def test_placeholder_route(client: AsyncClient) -> None:
    """占位路由：写入回显、读取回退默认值、重置、非法键 10001。"""
    put = await client.put(f"{API}/ui.theme", json={"value": {"mode": "dark"}})
    assert put.status_code == 200
    assert put.json()["data"] == {"key": "ui.theme", "value": {"mode": "dark"}}

    got = await client.get(f"{API}/ui.theme")
    assert got.status_code == 200
    assert got.json()["data"] == {"key": "ui.theme", "value": None}

    deleted = await client.delete(f"{API}/ui.theme")
    assert deleted.status_code == 200
    assert deleted.json()["data"] is None

    bad = await client.get(f"{API}/BadKey")
    assert bad.status_code == 200
    assert bad.json()["code"] == 10001
