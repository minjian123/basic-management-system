"""租户自助与品牌基座契约测试（Kiwi 891）：契约 / 常量 / 数据契约 / 占位语义 / 真实实现 / 路由。

11_01 起租户服务装配**真实实现**（`DbTenantSelfService`，provider `sql`）：`my_tenants` / `switch`
经关系数据源（本服务为 `local`：直读平台服务库 `sys_user_tenant`）取数并做越权校验；占位语义
（`NullTenantSelfService`）单独保留为契约基线用例。
"""

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

from bms_core.api.deps import current_code_of, get_idempotency_store
from bms_core.application import service_lifespan as lifespan
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.plugin import BasePluggable, resolve_plugin
from bms_core.db.tenant import DEMO_TENANT
from bms_core.idempotency.base import IDEMPOTENCY_PAYLOAD_TYPE
from bms_core.tenant.base import (
    DEFAULT_BRAND_PRIMARY_COLOR,
    TENANT_MEMBERSHIP_SELF_HEAL_SOURCE,
    TENANT_MEMBERSHIP_SOURCES,
    TENANT_MEMBERSHIP_STATUSES,
    TENANT_SELF_SERVICE_DB_PROVIDER,
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
from bms_core.tenant.db import DbTenantSelfService
from bms_core.tenant.null import NullTenantSelfService
from bms_tenant.api.tenant import router as tenant_router
from bms_tenant.main import ApplicationFactory
from tests_support.auth import auth_headers
from tests_support.tenant_source import DEMO_TENANT_ID
from tests_support.tenant_sql import grant_membership, membership_source

API = "/api/v1/tenants"

DEMO_CODE = "demo"
DEMO_NAME = "演示租户"
ACME_CODE = "acme"

_OTHER_USER = "9101"
"""与默认测试用户不同的用户主体（多租户用例，避免跨用例状态耦合）。"""

_ORPHAN_USER = "9201"
"""专用用户主体（「未建立关系」用例；不被其他用例自愈，避免跨用例状态耦合）。"""

_ORPHAN_DENIED_USER = "9301"
"""专用用户主体（「自愈后仍越权」用例；与 `_ORPHAN_USER` 分离，避免跨用例自愈状态耦合）。"""


class _RecordingIdempotency:
    """幂等基座测试替身：内存首次结果表。

    只按鸭子类型提供 `begin` / `load` / `save`（**不继承能力端口**，避免以占位名污染进程级注册表）。
    """

    def __init__(self) -> None:
        """初始化空首次结果表。"""
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()
        self._payloads: ConcurrentStableDict[str, IDEMPOTENCY_PAYLOAD_TYPE] = ConcurrentStableDict()

    async def begin(self, key: str, *, ttl: int | None = None) -> bool:
        """登记幂等键（首次为 True）。

        Args:
            key: 幂等键。
            ttl: 键有效期（替身忽略）。

        Returns:
            bool: 首次 True。
        """
        self.keys.add(key)
        return key not in self._payloads

    async def load(self, key: str) -> IDEMPOTENCY_PAYLOAD_TYPE | None:
        """取首次结果载荷。

        Args:
            key: 幂等键。

        Returns:
            IDEMPOTENCY_PAYLOAD_TYPE | None: 首次结果；未缓存为 None。
        """
        return self._payloads.get(key)

    async def save(self, key: str, payload: IDEMPOTENCY_PAYLOAD_TYPE, *, ttl: int | None = None) -> None:
        """写首次结果。

        Args:
            key: 幂等键。
            payload: 首次结果载荷。
            ttl: 键有效期（替身忽略）。
        """
        self._payloads.set(key, payload)


@pytest.mark.kiwi_id(891)
def test_contract_inheritance_and_identity() -> None:
    """契约继承链与能力域标识（含真实实现继承位）。"""
    assert issubclass(BaseTenantSelfService, BasePluggable)
    assert issubclass(BaseTenantSelfService, BaseCapability)
    assert issubclass(NullTenantSelfService, BaseTenantSelfService)
    assert issubclass(NullTenantSelfService, BaseNullObject)
    assert issubclass(DbTenantSelfService, BaseTenantSelfService)
    assert BaseTenantSelfService.key == "tenant_self_service"
    assert BaseTenantSelfService.plugin_key == "tenant_self_service"
    assert DbTenantSelfService.plugin_name == TENANT_SELF_SERVICE_DB_PROVIDER

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
    assert TENANT_MEMBERSHIP_SOURCES == (
        "super_admin",
        "admin_create",
        "import",
        "sso_jit",
        "self_register",
        "self_heal",
    )
    assert TENANT_MEMBERSHIP_SELF_HEAL_SOURCE == "self_heal"
    assert TENANT_MEMBERSHIP_STATUSES == ("active", "disabled")
    assert TENANT_SELF_SERVICE_DB_PROVIDER == "sql"

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

    other = await service.my_tenants(current_code="acme", tenant_id=2002, user_id=2)
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

    unknown = await service.switch("no-such-tenant", tenant_id=1, user_id=1)
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
    """依赖解析：租户服务装配真实实现（provider `sql`）；提供者解析到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        service = app.state.tenant_self_service
        assert isinstance(service, DbTenantSelfService)
        assert resolve_plugin("tenant_self_service", TENANT_SELF_SERVICE_DB_PROVIDER) is service
        assert app.state.plugin_providers["tenant_self_service"] == TENANT_SELF_SERVICE_DB_PROVIDER
        assert app.state.tenant_membership is not None


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
async def test_route_my_tenants_self_heals(client: AsyncClient, platform_db_url: str) -> None:
    """真实路由：我的租户——无可访问行时读路径自愈补建自有租户行（来源 `self_heal`）。"""
    resp = await client.get(f"{API}/mine")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["current_code"] == DEMO_CODE
    assert data["multi_tenant"] is False
    assert [item["code"] for item in data["tenants"]] == [DEMO_CODE]
    assert data["tenants"][0]["id"] == DEMO_TENANT_ID
    assert data["tenants"][0]["name"] == DEMO_NAME

    # 自愈补建行来源为 self_heal（幂等：重复调用不新增）
    assert await membership_source(platform_db_url, tenant_id=1001, user_id=1001) == (
        f"active|{TENANT_MEMBERSHIP_SELF_HEAL_SOURCE}"
    )
    again = await client.get(f"{API}/mine")
    assert [item["code"] for item in again.json()["data"]["tenants"]] == [DEMO_CODE]


@pytest.mark.kiwi_id(891)
async def test_route_my_tenants_multi_tenant(client: AsyncClient, platform_db_url: str) -> None:
    """真实路由：多租户——列出全部可访问租户且 `multi_tenant=true`。"""
    await grant_membership(
        platform_db_url, tenant_id=1001, user_id=int(_OTHER_USER), target_tenant_id=2002, source="admin_create"
    )
    client.headers.update(auth_headers(subject=_OTHER_USER))
    resp = await client.get(f"{API}/mine")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["multi_tenant"] is True
    assert sorted(item["code"] for item in data["tenants"]) == [ACME_CODE, DEMO_CODE]
    assert data["current_code"] == DEMO_CODE


@pytest.mark.kiwi_id(891)
async def test_route_switch_hit_and_denied(client: AsyncClient) -> None:
    """真实路由：切换命中（自有租户）/ 越权（未加入租户）/ 目标不存在 / 空编码。"""
    await client.get(f"{API}/mine")  # 读路径自愈：先建立自有租户关系

    hit = await client.post(f"{API}/switch", json={"code": DEMO_CODE})
    assert hit.status_code == 200
    data = hit.json()["data"]
    assert data["tenant_code"] == DEMO_CODE
    assert data["db_key"] == "tenant_demo"
    assert data["applied"] is True
    assert data["mode"] == "token"
    assert data["reissue_token"] is True
    assert data["token"] is None

    denied = await client.post(f"{API}/switch", json={"code": ACME_CODE})
    assert denied.status_code == 403
    assert denied.json()["code"] == 80003

    unknown = await client.post(f"{API}/switch", json={"code": "no-such-tenant"})
    assert unknown.status_code == 404
    assert unknown.json()["code"] == 80001

    invalid = await client.post(f"{API}/switch", json={"code": "   "})
    assert invalid.json()["code"] == 10001


@pytest.mark.kiwi_id(891)
async def test_route_switch_self_heals_without_prior_my_tenants(client: AsyncClient, platform_db_url: str) -> None:
    """真实路由：未先经 `my_tenants` 时直接切自有租户——`switch` 同出口自愈后命中（200）。"""
    client.headers.update(auth_headers(subject=_ORPHAN_USER))
    hit = await client.post(f"{API}/switch", json={"code": DEMO_CODE})
    assert hit.status_code == 200, hit.text
    data = hit.json()["data"]
    assert data["tenant_code"] == DEMO_CODE
    assert data["db_key"] == "tenant_demo"
    assert data["applied"] is True
    assert data["reissue_token"] is True
    # 自愈补建的是自有租户行（来源 self_heal），无需先调 my_tenants
    assert await membership_source(platform_db_url, tenant_id=1001, user_id=int(_ORPHAN_USER)) == (
        f"active|{TENANT_MEMBERSHIP_SELF_HEAL_SOURCE}"
    )


@pytest.mark.kiwi_id(891)
async def test_route_switch_denied_after_self_heal(client: AsyncClient, platform_db_url: str) -> None:
    """真实路由：自愈只补自有租户行——未接线用户直接切他人租户仍被拒（403 / 80003）。"""
    client.headers.update(auth_headers(subject=_ORPHAN_DENIED_USER))
    denied = await client.post(f"{API}/switch", json={"code": ACME_CODE})
    assert denied.status_code == 403, denied.text
    assert denied.json()["code"] == 80003
    # 自愈不构成越权放宽：自有租户行已建立，他人租户仍不可达
    assert await membership_source(platform_db_url, tenant_id=1001, user_id=int(_ORPHAN_DENIED_USER)) == (
        f"active|{TENANT_MEMBERSHIP_SELF_HEAL_SOURCE}"
    )


@pytest.mark.kiwi_id(891)
@pytest.mark.kiwi_id(2218)
async def test_switch_idempotency_reuses_first_result() -> None:
    """切换按幂等键复用首次结果（作用域绑当前租户位）。"""
    app = ApplicationFactory().create(None)
    double = _RecordingIdempotency()
    app.dependency_overrides[get_idempotency_store] = lambda: double
    async with lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers.update(auth_headers())
        await client.get(f"{API}/mine")  # 自愈：建立自有租户关系
        first = await client.post(f"{API}/switch", json={"code": DEMO_CODE}, headers={"Idempotency-Key": "k-1"})
        second = await client.post(f"{API}/switch", json={"code": ACME_CODE}, headers={"Idempotency-Key": "k-1"})

    assert first.json()["data"]["tenant_code"] == DEMO_CODE
    assert second.json()["data"] == first.json()["data"]
    assert double.keys == [f"bms:{DEMO_TENANT_ID}:idem:k-1", f"bms:{DEMO_TENANT_ID}:idem:k-1"]


@pytest.mark.kiwi_id(891)
async def test_route_brand_without_auth(client: AsyncClient) -> None:
    """真实路由：品牌信息登录前可用（免登录），带 / 不带编码结果一致（本任务不做品牌取数）。"""
    resp = await client.get(f"{API}/brand")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == DEMO_NAME
    assert data["primary_color"] == DEFAULT_BRAND_PRIMARY_COLOR
    assert data["default_mode"] == "system"
    assert data["allow_user_accent"] is True
    assert data["disable_dark"] is False

    with_code = await client.get(f"{API}/brand", params={"code": ACME_CODE})
    assert with_code.json()["data"] == data
