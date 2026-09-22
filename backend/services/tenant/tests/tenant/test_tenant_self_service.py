"""租户自助与品牌基座契约测试（Kiwi 891）：契约 / 常量 / 数据契约 / 占位语义 / 依赖解析 / 占位路由。"""

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import current_code_of, get_idempotency_store
from bms_core.application import service_lifespan as lifespan
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.db.tenant import DEMO_TENANT
from bms_core.tenant.base import (
    DEFAULT_BRAND_PRIMARY_COLOR,
    TENANT_STATUSES,
    TENANT_SWITCH_MODES,
    THEME_MODES,
    BaseTenantSelfService,
    TenantBrand,
    TenantSelfOverview,
    TenantSummary,
    TenantSwitchResult,
    build_tenant_db_key,
)
from bms_core.tenant.null import NullTenantSelfService
from bms_tenant.api.tenant import router as tenant_router
from bms_tenant.main import ApplicationFactory

API = "/api/v1/tenants"

DEMO_CODE = "demo"
DEMO_NAME = "演示租户"


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表。

    只按鸭子类型提供 `begin` / `load` / `save`（**不继承能力端口**，避免以占位名污染进程级注册表）。
    """

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
        self._payloads[key] = payload


@pytest.mark.kiwi_id(891)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识。"""
    assert issubclass(BaseTenantSelfService, BasePluggable)
    assert issubclass(BaseTenantSelfService, BaseCapability)
    assert issubclass(NullTenantSelfService, BaseTenantSelfService)
    assert issubclass(NullTenantSelfService, BaseNullObject)
    assert BaseTenantSelfService.key == "tenant_self_service"
    assert BaseTenantSelfService.plugin_key == "tenant_self_service"

    service = NullTenantSelfService()
    assert service.placeholder is True
    assert "占位实现" in service.describe()


@pytest.mark.kiwi_id(891)
def test_constants_and_db_key() -> None:
    """取值集合常量与数据源键助手。"""
    assert THEME_MODES == ("light", "dark", "system")
    assert TENANT_STATUSES == ("active", "suspended")
    assert TENANT_SWITCH_MODES == ("token", "session")
    assert DEFAULT_BRAND_PRIMARY_COLOR == "#1677ff"

    assert build_tenant_db_key("demo") == "tenant_demo"
    assert build_tenant_db_key("acme") == "tenant_acme"


@pytest.mark.kiwi_id(891)
def test_data_contract_defaults() -> None:
    """四数据契约字段口径与缺省值。"""
    summary = TenantSummary(id="1", name="甲租户")
    assert summary.code is None
    assert summary.logo is None
    assert summary.role_name is None

    overview = TenantSelfOverview()
    assert overview.tenants == []
    assert overview.current_code is None
    assert overview.multi_tenant is False

    result = TenantSwitchResult(tenant_code="acme", db_key="tenant_acme")
    assert result.applied is True
    assert result.mode == "token"
    assert result.reissue_token is False
    assert result.token is None

    brand = TenantBrand()
    assert brand.name is None
    assert brand.logo is None
    assert brand.favicon is None
    assert brand.primary_color == DEFAULT_BRAND_PRIMARY_COLOR
    assert brand.default_mode == "system"
    assert brand.login_bg is None
    assert brand.allow_user_accent is True
    assert brand.disable_dark is False


@pytest.mark.kiwi_id(891)
async def test_null_my_tenants_fixed_single_tenant() -> None:
    """占位「我的租户」：固定单租户、当前租户固定演示租户（忽略入参）。"""
    service = NullTenantSelfService()

    overview = await service.my_tenants()
    assert overview.multi_tenant is False
    assert overview.current_code == DEMO_CODE
    assert len(overview.tenants) == 1
    assert overview.tenants[0].id == DEMO_CODE
    assert overview.tenants[0].code == DEMO_CODE
    assert overview.tenants[0].name == DEMO_NAME

    other = await service.my_tenants(current_code="acme")
    assert other.current_code == DEMO_CODE


@pytest.mark.kiwi_id(891)
async def test_null_switch_echoes_without_side_effect() -> None:
    """占位切换：恒定回显（不校验存在性）、零副作用、结果一致。"""
    service = NullTenantSelfService()

    result = await service.switch("acme")
    assert result.tenant_code == "acme"
    assert result.db_key == "tenant_acme"
    assert result.applied is True
    assert result.mode == TENANT_SWITCH_MODES[0]
    assert result.reissue_token is False
    assert result.token is None

    unknown = await service.switch("no-such-tenant")
    assert unknown.applied is True
    assert unknown.db_key == "tenant_no-such-tenant"
    assert unknown == await service.switch("no-such-tenant")


@pytest.mark.kiwi_id(891)
async def test_null_brand_platform_default() -> None:
    """占位品牌：固定平台默认品牌，不区分租户编码。"""
    service = NullTenantSelfService()

    brand = await service.brand()
    assert brand.name == DEMO_NAME
    assert brand.primary_color == DEFAULT_BRAND_PRIMARY_COLOR
    assert brand.default_mode == "system"
    assert brand.allow_user_accent is True
    assert brand.disable_dark is False

    assert await service.brand(code="acme") == brand


@pytest.mark.kiwi_id(891)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位服务；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        service = app.state.tenant_self_service
        assert isinstance(service, NullTenantSelfService)
        assert resolve_plugin("tenant_self_service", None) is service
        assert app.state.plugin_providers["tenant_self_service"] == "null"


@pytest.mark.kiwi_id(891)
def test_current_code_of_helper() -> None:
    """当前租户编码助手：有上下文取编码、解析链豁免路径（无上下文）为空。"""
    assert current_code_of(None) is None
    assert current_code_of(DEMO_TENANT) == DEMO_CODE


@pytest.mark.kiwi_id(891)
def test_route_auth_scope() -> None:
    """登录口径：我的租户 / 切换挂登录依赖，品牌免登录。"""
    routes = [route for route in tenant_router.routes if isinstance(route, APIRoute)]
    deps = {route.path: len(route.dependencies) for route in routes}
    assert deps == {"/tenants/mine": 1, "/tenants/switch": 1, "/tenants/brand": 0}


@pytest.mark.kiwi_id(891)
async def test_placeholder_route_my_tenants(client: AsyncClient) -> None:
    """占位路由：我的租户概览（当前租户取自解析链上下文）。"""
    resp = await client.get(f"{API}/mine")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["multi_tenant"] is False
    assert data["current_code"] == DEMO_CODE
    assert [item["id"] for item in data["tenants"]] == [DEMO_CODE]
    assert data["tenants"][0]["name"] == DEMO_NAME


@pytest.mark.kiwi_id(891)
async def test_placeholder_route_switch(client: AsyncClient) -> None:
    """占位路由：切换结果回显、空编码 10001、无幂等键亦可用。"""
    resp = await client.post(f"{API}/switch", json={"code": "acme"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant_code"] == "acme"
    assert data["db_key"] == "tenant_acme"
    assert data["applied"] is True
    assert data["mode"] == "token"
    assert data["reissue_token"] is False
    assert data["token"] is None

    invalid = await client.post(f"{API}/switch", json={"code": "   "})
    assert invalid.json()["code"] == 10001


@pytest.mark.kiwi_id(891)
async def test_switch_idempotency_reuses_first_result() -> None:
    """切换按幂等键复用首次结果（作用域绑当前租户位）。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(f"{API}/switch", json={"code": "acme"}, headers={"Idempotency-Key": "k-1"})
        second = await client.post(f"{API}/switch", json={"code": "other"}, headers={"Idempotency-Key": "k-1"})

    assert first.json()["data"]["tenant_code"] == "acme"
    assert second.json()["data"] == first.json()["data"]
    assert double.keys == [f"bms:{DEMO_CODE}:idem:k-1", f"bms:{DEMO_CODE}:idem:k-1"]


@pytest.mark.kiwi_id(891)
async def test_placeholder_route_brand_without_auth(client: AsyncClient) -> None:
    """占位路由：品牌信息登录前可用（免登录），带 / 不带编码结果一致。"""
    resp = await client.get(f"{API}/brand")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == DEMO_NAME
    assert data["primary_color"] == DEFAULT_BRAND_PRIMARY_COLOR
    assert data["default_mode"] == "system"
    assert data["allow_user_accent"] is True
    assert data["disable_dark"] is False

    with_code = await client.get(f"{API}/brand", params={"code": "acme"})
    assert with_code.json()["data"] == data
