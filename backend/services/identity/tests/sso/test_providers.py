"""SSO 入口清单端点测试（Kiwi 2197）：按租户返回启用提供方 + 租户解析分支。

单库叠加口径（04-6-2）：入口清单是**整租户集合**口径（端点无编码前缀筛选），断言一律先按本用例
命名空间前缀裁剪再比对（§6.3「集合先按前缀裁剪」），不假定库为空。
"""

import pytest
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.tenant import TenantContext
from bms_core.testing.namespace import Namespace

from .conftest import SsoHarness

API = "/api/v1/auth/sso/providers"
TENANT_HEADERS: ConcurrentStableDict[str, str] = ConcurrentStableDict({"X-Tenant-ID": "demo"})


def _mine(  # bare-collections:allow（端点返回的 JSON 行，仅按前缀裁剪）
    items: list[dict[str, object]], ns: Namespace
) -> list[dict[str, object]]:  # bare-collections:allow（端点返回的 JSON 行，仅按前缀裁剪）
    """裁剪出本用例命名空间内的入口项。

    Args:
        items: 端点返回的入口清单。
        ns: 用例命名空间。

    Returns:
        list[dict[str, object]]: 仅本用例的行（保持端点给出的顺序）。
    """
    return [item for item in items if str(item.get("idp_key", "")).startswith(ns.prefix)]


@pytest.mark.kiwi_id(2197)
async def test_list_providers_sorted_and_disabled_filtered(client: AsyncClient, sso: SsoHarness, ns: Namespace) -> None:
    """入口清单：仅启用项，按 sort 升序；停用项不出现。"""
    empty = await client.get(API, headers=TENANT_HEADERS)
    assert empty.status_code == 200 and _mine(empty.json()["data"]["items"], ns) == []

    keys = [ns.code("b"), ns.code("a"), ns.code("off")]
    await sso.seed_provider(idp_key=keys[0], sort=2, name="B 身份源")
    await sso.seed_provider(idp_key=keys[1], sort=1, name="A 身份源")
    await sso.seed_provider(idp_key=keys[2], sort=0, name="停用身份源", status="disabled")

    response = await client.get(API, headers=TENANT_HEADERS)
    assert response.status_code == 200
    items = _mine(response.json()["data"]["items"], ns)
    assert [item["idp_key"] for item in items] == [keys[1], keys[0]]
    assert items[0] == {"idp_key": keys[1], "name": "A 身份源", "icon": "", "type": "oidc", "sort": 1}


@pytest.mark.kiwi_id(2197)
async def test_list_providers_no_tenant_returns_empty(client: AsyncClient, sso: SsoHarness) -> None:
    """租户解析：无请求头、无 tenant 参数且多启用租户 → 空清单（不报错，不暴露目录）。"""
    sso.app.state.settings.tenant.allow_demo_fallback = False
    response = await client.get(API)
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.kiwi_id(2239)
async def test_list_providers_single_active_fallback(
    client: AsyncClient, sso: SsoHarness, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """租户解析：无请求头且唯一启用租户 → 按该租户返回入口清单（免登录首访可见）。"""
    sso.app.state.settings.tenant.allow_demo_fallback = False
    key = ns.code("a")
    await sso.seed_provider(idp_key=key, sort=1, name="A 身份源")
    source = sso.app.state.tenant_source

    async def fake_single_active() -> TenantContext:
        return await source.by_code("demo")

    monkeypatch.setattr(source, "single_active", fake_single_active)

    response = await client.get(API)
    assert response.status_code == 200
    assert [item["idp_key"] for item in _mine(response.json()["data"]["items"], ns)] == [key]


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
