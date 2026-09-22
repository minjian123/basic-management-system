"""自定义图标基座契约测试（Kiwi 927）：契约 / 常量与键助手 / 数据契约 / 占位语义 / 表声明 / 依赖解析 / 占位路由。"""

from typing import cast

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Table, UniqueConstraint

from bms_core.api.deps import get_idempotency_store
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.error_codes import ErrorCode
from bms_core.core.exceptions import NotFoundError
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.icon.base import (
    DEFAULT_ICON_STATUS,
    ICON_CODE_MAX_LENGTH,
    ICON_CUSTOM_SOURCE,
    ICON_KEY_SEPARATOR,
    ICON_NAME_MAX_LENGTH,
    ICON_SOURCES,
    ICON_STATUSES,
    ICON_SVG_MAX_BYTES,
    NULL_ICON_ID_PREFIX,
    BaseIconRegistry,
    IconDraft,
    IconInfo,
    IconPatch,
    build_icon_key,
    is_valid_icon_code,
)
from bms_core.icon.null import NullIconRegistry
from bms_platform.api.icon import router as icon_router
from bms_platform.main import ApplicationFactory, lifespan
from bms_platform.models.system import SysIcon, SysIconI18n

API = "/api/v1/icons"

_ICON_BODY = {"code": "purchase-order", "name": "采购订单", "category": "menu", "tags": ["order"], "svg": "<svg/>"}


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表（不继承能力端口，避免以占位名污染进程级注册表）。"""

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: list[str] = []
        self._payloads: dict[str, dict[str, object]] = {}

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次为 True）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        del ttl
        self.keys.append(key)
        return key not in self._payloads

    async def load(self, key: str) -> dict[str, object] | None:
        """取首次结果载荷。

        Args:
            key: 幂等键。

        Returns:
            dict[str, object] | None: 首次结果；未缓存为 None。
        """
        return self._payloads.get(key)

    async def save(self, key: str, payload: dict[str, object], *, ttl: int | None = None) -> None:
        """写首次结果。

        Args:
            key: 幂等键。
            payload: 首次结果载荷。
            ttl: 键有效期（替身忽略）。
        """
        del ttl
        self._payloads[key] = payload


class _StaleIdempotency(_RecordingIdempotency):
    """幂等基座替身：非首次且首次结果不可读（占位期并发穿透，应继续执行）。"""

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键并恒返回非首次。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 恒 False（非首次）。
        """
        await super().begin(key, ttl=ttl)
        return False

    async def load(self, key: str) -> dict[str, object] | None:
        """取首次结果（恒不可读）。

        Args:
            key: 幂等键。

        Returns:
            dict[str, object] | None: 恒 None。
        """
        del key
        return None


@pytest.mark.kiwi_id(927)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BaseIconRegistry, BasePluggable)
    assert issubclass(BaseIconRegistry, BaseCapability)
    assert issubclass(NullIconRegistry, BaseIconRegistry)
    assert issubclass(NullIconRegistry, BaseNullObject)
    assert BaseIconRegistry.key == "icon_registry"
    assert BaseIconRegistry.plugin_key == "icon_registry"

    instance = NullIconRegistry()
    assert instance.placeholder is True
    assert "占位实现" in instance.describe()


@pytest.mark.kiwi_id(927)
def test_constants() -> None:
    """取值集合与口径常量。"""
    assert ICON_SOURCES == ("el", "biz", "custom", "van")
    assert ICON_CUSTOM_SOURCE == "custom"
    assert ICON_KEY_SEPARATOR == ":"
    assert ICON_STATUSES == ("active", "disabled")
    assert DEFAULT_ICON_STATUS == "active"
    assert ICON_CODE_MAX_LENGTH == 64
    assert ICON_NAME_MAX_LENGTH == 128
    assert ICON_SVG_MAX_BYTES == 102400
    assert NULL_ICON_ID_PREFIX == "null-"


@pytest.mark.kiwi_id(927)
def test_icon_key_helper_and_code_validation() -> None:
    """图标键派生与图标键格式校验。"""
    assert build_icon_key("purchase-order") == "custom:purchase-order"
    assert build_icon_key("receipt", source="biz") == "biz:receipt"

    assert is_valid_icon_code("purchase-order") is True
    assert is_valid_icon_code("receipt") is True
    assert is_valid_icon_code("a1-b2-c3") is True

    assert is_valid_icon_code("") is False
    assert is_valid_icon_code("Purchase-Order") is False
    assert is_valid_icon_code("purchase_order") is False
    assert is_valid_icon_code("1receipt") is False
    assert is_valid_icon_code("-receipt") is False
    assert is_valid_icon_code("receipt-") is False
    assert is_valid_icon_code("purchase--order") is False
    assert is_valid_icon_code("a" * (ICON_CODE_MAX_LENGTH + 1)) is False


@pytest.mark.kiwi_id(927)
def test_data_contract_defaults() -> None:
    """三数据契约字段口径与缺省值。"""
    draft = IconDraft(code="receipt", name="票据", category="menu", svg="<svg/>")
    assert draft.tags == []

    patch = IconPatch()
    assert patch.name is None
    assert patch.category is None
    assert patch.tags is None
    assert patch.svg is None
    assert patch.status is None

    info = IconInfo(id="i-1", code="receipt", name="票据", category="menu", svg="<svg/>", icon_key="custom:receipt")
    assert info.tags == []
    assert info.status == DEFAULT_ICON_STATUS


@pytest.mark.kiwi_id(927)
async def test_null_list_is_empty() -> None:
    """占位图标清单：固定空清单，不区分过滤参数。"""
    registry = NullIconRegistry()

    assert await registry.list() == []
    assert await registry.list(category="menu", status="active", keyword="purchase") == []


@pytest.mark.kiwi_id(927)
async def test_null_get_not_found() -> None:
    """占位图标详情：恒定未命中（10002 / 404）。"""
    with pytest.raises(NotFoundError) as excinfo:
        await NullIconRegistry().get("receipt")

    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert excinfo.value.http_status == 404
    assert "receipt" in str(excinfo.value)


@pytest.mark.kiwi_id(927)
async def test_null_create_placeholder() -> None:
    """占位图标新增：回显入参、标识由图标键派生、零副作用。"""
    draft = IconDraft(code="receipt", name="票据", category="menu", tags=["doc"], svg="<svg/>")
    registry = NullIconRegistry()

    info = await registry.create(draft)
    assert info == IconInfo(
        id=f"{NULL_ICON_ID_PREFIX}receipt",
        code="receipt",
        name="票据",
        category="menu",
        tags=["doc"],
        svg="<svg/>",
        status=DEFAULT_ICON_STATUS,
        icon_key="custom:receipt",
    )
    assert await registry.create(draft) == info
    assert draft.tags == ["doc"]


@pytest.mark.kiwi_id(927)
async def test_null_update_placeholder() -> None:
    """占位图标更新：提供字段回显、未提供字段回落占位值。"""
    registry = NullIconRegistry()

    patched = await registry.update("receipt", IconPatch(name="新票据", tags=["doc"], status="disabled"))
    assert patched.id == f"{NULL_ICON_ID_PREFIX}receipt"
    assert patched.name == "新票据"
    assert patched.category == ""
    assert patched.tags == ["doc"]
    assert patched.svg == ""
    assert patched.status == "disabled"
    assert patched.icon_key == "custom:receipt"

    fallback = await registry.update("receipt", IconPatch())
    assert fallback.name == "receipt"
    assert fallback.category == ""
    assert fallback.tags == []
    assert fallback.svg == ""
    assert fallback.status == DEFAULT_ICON_STATUS


@pytest.mark.kiwi_id(927)
async def test_null_delete_returns_true() -> None:
    """占位图标删除：恒定 True（幂等删除语义）。"""
    registry = NullIconRegistry()

    assert await registry.delete("receipt") is True
    assert await registry.delete("receipt") is True


@pytest.mark.kiwi_id(927)
def test_table_declaration() -> None:
    """表声明：`sys_icon` / `sys_icon_i18n` 表名、关键字段与含 deleted_at 的唯一约束。"""
    assert SysIcon.__tablename__ == "sys_icon"
    for field_name in ("code", "name", "category", "tags", "svg", "status"):
        assert field_name in SysIcon.__table__.columns

    assert SysIconI18n.__tablename__ == "sys_icon_i18n"
    for field_name in ("icon_id", "locale", "name"):
        assert field_name in SysIconI18n.__table__.columns

    icon_uniques = [item for item in cast("Table", SysIcon.__table__).constraints if isinstance(item, UniqueConstraint)]
    assert [item.name for item in icon_uniques] == ["uq_sys_icon_code_deleted_at"]
    assert "deleted_at" in {column.name for column in icon_uniques[0].columns}

    i18n_table = cast("Table", SysIconI18n.__table__)
    i18n_uniques = [item for item in i18n_table.constraints if isinstance(item, UniqueConstraint)]
    assert [item.name for item in i18n_uniques] == ["uq_sys_icon_i18n_icon_locale_deleted_at"]
    assert "deleted_at" in {column.name for column in i18n_uniques[0].columns}


@pytest.mark.kiwi_id(927)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位实现与提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        registry = app.state.icon_registry
        assert isinstance(registry, NullIconRegistry)
        assert resolve_plugin("icon_registry", None) is registry
        assert app.state.plugin_providers["icon_registry"] == "null"


@pytest.mark.kiwi_id(927)
def test_route_auth_scope() -> None:
    """登录口径：五端点均挂登录依赖（路由级统一）。"""
    routes = [route for route in icon_router.routes if isinstance(route, APIRoute)]
    assert icon_router.key == "icon"
    assert {route.path for route in routes} == {"/icons", "/icons/{code}"}
    assert {route.path: len(route.dependencies) for route in routes} == {
        "/icons": 1,
        "/icons/{code}": 1,
    }


@pytest.mark.kiwi_id(927)
async def test_placeholder_route_list_and_get(client: AsyncClient) -> None:
    """占位路由：图标清单为空、详情 404 且业务码 10002、图标键格式非法 → 10001。"""
    listed = await client.get(API)
    assert listed.status_code == 200
    assert listed.json()["data"] == {"icons": []}

    filtered = await client.get(API, params={"category": "menu", "status": "active", "keyword": "purchase"})
    assert filtered.json()["data"] == {"icons": []}

    missing = await client.get(f"{API}/purchase-order")
    assert missing.status_code == 404
    assert missing.json()["code"] == ErrorCode.NOT_FOUND

    invalid = await client.get(f"{API}/Bad_Code")
    assert invalid.json()["code"] == ErrorCode.PARAM


@pytest.mark.kiwi_id(927)
async def test_placeholder_route_create_update_delete(client: AsyncClient) -> None:
    """占位路由：新增回显、更新回显与回落、删除结果、图标键格式非法 → 10001。"""
    created = await client.post(API, json=_ICON_BODY)
    assert created.status_code == 200
    assert created.json()["data"] == {
        "id": f"{NULL_ICON_ID_PREFIX}purchase-order",
        "code": "purchase-order",
        "name": "采购订单",
        "category": "menu",
        "tags": ["order"],
        "svg": "<svg/>",
        "status": DEFAULT_ICON_STATUS,
        "icon_key": "custom:purchase-order",
    }

    patched = await client.put(f"{API}/purchase-order", json={"name": "采购订单（新）", "status": "disabled"})
    assert patched.json()["data"]["name"] == "采购订单（新）"
    assert patched.json()["data"]["category"] == ""
    assert patched.json()["data"]["tags"] == []
    assert patched.json()["data"]["status"] == "disabled"

    fallback = await client.put(f"{API}/purchase-order", json={})
    assert fallback.json()["data"]["name"] == "purchase-order"
    assert fallback.json()["data"]["status"] == DEFAULT_ICON_STATUS

    removed = await client.delete(f"{API}/purchase-order")
    assert removed.json()["data"] == {"deleted": True}

    invalid = await client.post(API, json={**_ICON_BODY, "code": "Bad_Code"})
    assert invalid.json()["code"] == ErrorCode.PARAM

    invalid_delete = await client.delete(f"{API}/Bad_Code")
    assert invalid_delete.json()["code"] == ErrorCode.PARAM


@pytest.mark.kiwi_id(927)
async def test_icon_create_idempotency_first_call_and_reuse() -> None:
    """新增：幂等键首次登记执行并缓存，重复提交复用首次结果（作用域绑当前租户位）。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(API, json=_ICON_BODY, headers={"Idempotency-Key": "k-1"})
        second = await client.post(API, json={**_ICON_BODY, "name": "其他"}, headers={"Idempotency-Key": "k-1"})

    assert first.json()["data"]["name"] == "采购订单"
    assert second.json()["data"] == first.json()["data"]
    assert double.keys == ["bms:demo:idem:k-1", "bms:demo:idem:k-1"]


@pytest.mark.kiwi_id(927)
async def test_icon_update_idempotency_without_cached_result_executes() -> None:
    """更新：幂等键非首次但首次结果不可读时继续执行（并发穿透不阻断）。"""
    app = ApplicationFactory().create(None)
    stale = _StaleIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: stale
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(f"{API}/purchase-order", json={"name": "新名称"}, headers={"Idempotency-Key": "k-2"})

    assert resp.json()["data"]["name"] == "新名称"
    assert stale.keys == ["bms:demo:idem:k-2"]


@pytest.mark.kiwi_id(927)
async def test_icon_update_and_delete_idempotency_reuse() -> None:
    """更新与删除：重复提交按幂等键复用首次结果。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        updated = await client.put(f"{API}/purchase-order", json={"name": "甲"}, headers={"Idempotency-Key": "k-3"})
        updated_again = await client.put(
            f"{API}/purchase-order", json={"name": "乙"}, headers={"Idempotency-Key": "k-3"}
        )
        removed = await client.delete(f"{API}/receipt", headers={"Idempotency-Key": "k-4"})
        removed_again = await client.delete(f"{API}/receipt", headers={"Idempotency-Key": "k-4"})

    assert updated.json()["data"]["name"] == "甲"
    assert updated_again.json()["data"] == updated.json()["data"]
    assert removed.json()["data"] == {"deleted": True}
    assert removed_again.json()["data"] == removed.json()["data"]
    assert double.keys == ["bms:demo:idem:k-3", "bms:demo:idem:k-3", "bms:demo:idem:k-4", "bms:demo:idem:k-4"]
