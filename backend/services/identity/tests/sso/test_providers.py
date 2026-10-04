"""SSO 入口清单端点测试（Kiwi 2197）：按租户返回启用提供方 + 租户解析分支。"""

import pytest
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.tenant import TenantContext

from .conftest import SsoHarness

API = "/api/v1/auth/sso/providers"
TENANT_HEADERS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": "demo"})


@pytest.mark.kiwi_id(2197)
async def test_list_providers_sorted_and_disabled_filtered(client: AsyncClient, sso: SsoHarness) -> None:
    """入口清单：仅启用项，按 sort 升序；无可选项返回空列表。"""
    empty = await client.get(API, headers=TENANT_HEADERS)
    assert empty.status_code == 200 and empty.json()["data"]["items"] == []

    await sso.seed_provider(idp_key="b", sort=2, name="B 身份源")
    await sso.seed_provider(idp_key="a", sort=1, name="A 身份源")
    await sso.seed_provider(idp_key="off", sort=0, name="停用身份源", status="disabled")

    response = await client.get(API, headers=TENANT_HEADERS)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert [item["idp_key"] for item in items] == ["a", "b"]
    assert items[0] == {"idp_key": "a", "name": "A 身份源", "icon": "", "type": "oidc", "sort": 1}


@pytest.mark.kiwi_id(2197)
async def test_list_providers_no_tenant_returns_empty(client: AsyncClient, sso: SsoHarness) -> None:
    """租户解析：无请求头、无 tenant 参数且多启用租户 → 空清单（不报错，不暴露目录）。"""
    sso.app.state.settings.tenant.allow_demo_fallback = False
    response = await client.get(API)
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.kiwi_id(2239)
async def test_list_providers_single_active_fallback(
    client: AsyncClient, sso: SsoHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """租户解析：无请求头且唯一启用租户 → 按该租户返回入口清单（免登录首访可见）。"""
    sso.app.state.settings.tenant.allow_demo_fallback = False
    await sso.seed_provider(idp_key="a", sort=1, name="A 身份源")
    source = sso.app.state.tenant_source

    async def fake_single_active() -> TenantContext:
        return await source.by_code("demo")

    monkeypatch.setattr(source, "single_active", fake_single_active)

    response = await client.get(API)
    assert response.status_code == 200
    assert [item["idp_key"] for item in response.json()["data"]["items"]] == ["a"]


@pytest.mark.kiwi_id(2197)
async def test_list_providers_tenant_mismatch(
    client: AsyncClient, sso: SsoHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """租户解析：上下文租户与 tenant 参数不一致 → 404（20051）。"""
    source = sso.app.state.tenant_source
    original = source.by_code

    async def fake_by_code(code: str) -> TenantContext:
        if code == "other":
            return TenantContext(code="other", db_key="tenant_other", name="其他租户")
        return await original(code)

    monkeypatch.setattr(source, "by_code", fake_by_code)
    response = await client.get(f"{API}?tenant=demo", headers={"X-Tenant-ID": "other"})
    assert response.status_code == 404
    assert response.json()["code"] == 20051

    ok = await client.get(f"{API}?tenant=demo")
    assert ok.status_code == 200
