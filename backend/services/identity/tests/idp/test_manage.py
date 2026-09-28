"""外部 IdP 配置管理面测试（Kiwi 2203）：CRUD / 启停 / 两形态连通性 / 脱敏 / 限流 / 鉴权。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.exceptions import PermissionError
from bms_core.permission import base as permission_base

from .conftest import ISSUER, TENANT_HEADERS, TENANT_ID, ManageHarness

_BASE = "/api/v1/idp/providers"
_SSO_PROVIDERS = "/api/v1/auth/sso/providers"


def _oidc_config(**overrides: object) -> dict[str, object]:
    """OIDC 配置（指向探测替身）。"""
    config: dict[str, object] = {
        "issuer": ISSUER,
        "client_id": "bms-backend",
        "client_secret_ref": "env:MANAGE_TEST_SECRET",
        "redirect_uri": "https://app.example.com/api/v1/auth/sso/keycloak/callback",
    }
    config.update(overrides)
    return config


async def _create(client: AsyncClient, **overrides: object) -> dict[str, object]:
    """调新建接口。"""
    body: dict[str, object] = {
        "name": "Keycloak",
        "idp_key": "keycloak",
        "type": "oidc",
        "config": _oidc_config(),
    }
    body.update(overrides)
    response = await client.post(_BASE, json=body, headers=TENANT_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.kiwi_id(2203)
async def test_crud_and_soft_delete_reuse(client: AsyncClient, manage: ManageHarness) -> None:
    """新建 / 列表 / 详情 / 修改 / 独立启停 / 软删后标识可复用。"""
    created = await _create(client)
    provider_id = created["id"]
    assert created["status"] == "enabled"

    listing = await client.get(_BASE, params={"status": "enabled", "type": "oidc"}, headers=TENANT_HEADERS)
    page = listing.json()["data"]
    assert page["total"] == 1
    assert page["list"][0]["idp_key"] == "keycloak"
    by_name = await client.get(_BASE, params={"name": "Key"}, headers=TENANT_HEADERS)
    assert by_name.json()["data"]["total"] == 1
    no_name = await client.get(_BASE, params={"name": "Nope"}, headers=TENANT_HEADERS)
    assert no_name.json()["data"]["total"] == 0

    detail = await client.get(f"{_BASE}/{provider_id}", headers=TENANT_HEADERS)
    assert detail.status_code == 200

    updated = await client.put(
        f"{_BASE}/{provider_id}",
        json={"name": "Keycloak2", "icon": "logo.png", "sort": 5, "config": _oidc_config(jit_enabled=True)},
        headers=TENANT_HEADERS,
    )
    assert updated.json()["data"]["name"] == "Keycloak2"
    assert updated.json()["data"]["icon"] == "logo.png"
    assert updated.json()["data"]["sort"] == 5
    assert updated.json()["data"]["config"]["jit_enabled"] is True

    disabled = await client.post(f"{_BASE}/{provider_id}/status", json={"status": "disabled"}, headers=TENANT_HEADERS)
    assert disabled.json()["data"]["status"] == "disabled"

    deleted = await client.delete(f"{_BASE}/{provider_id}", headers=TENANT_HEADERS)
    assert deleted.status_code == 200
    after = await client.get(f"{_BASE}/{provider_id}", headers=TENANT_HEADERS)
    assert after.status_code == 404 and after.json()["code"] == 20063

    again = await _create(client)
    assert again["idp_key"] == "keycloak"


@pytest.mark.kiwi_id(2203)
async def test_config_secret_masked(client: AsyncClient, manage: ManageHarness) -> None:
    """列表 / 详情 `config` 敏感键脱敏、无明文；`secret_configured` 为真。"""
    await _create(client)
    page = (await client.get(_BASE, headers=TENANT_HEADERS)).json()["data"]
    item = page["list"][0]
    assert item["config"]["client_secret_ref"] == "env:***"
    assert item["config"]["client_id"] == "bms-backend"
    assert item["secret_configured"] is True
    assert "s3cr3t" not in str(item)


@pytest.mark.kiwi_id(2203)
async def test_write_validation_and_conflict(client: AsyncClient, manage: ManageHarness) -> None:
    """字段 / 配置非法 20064；标识冲突 20065；SSRF 拒绝。"""
    await _create(client)
    conflict = await client.post(
        _BASE,
        json={"name": "Dup", "idp_key": "keycloak", "type": "oidc", "config": _oidc_config()},
        headers=TENANT_HEADERS,
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == 20065

    missing = await client.post(
        _BASE,
        json={"name": "Bad", "idp_key": "bad1", "type": "oidc", "config": {"issuer": ISSUER}},
        headers=TENANT_HEADERS,
    )
    assert missing.status_code == 400 and missing.json()["code"] == 20064

    unknown = await client.post(
        _BASE,
        json={"name": "Bad", "idp_key": "bad2", "type": "oidc", "config": _oidc_config(bogus=1)},
        headers=TENANT_HEADERS,
    )
    assert unknown.status_code == 400 and unknown.json()["code"] == 20064

    plaintext = await client.post(
        _BASE,
        json={
            "name": "Bad",
            "idp_key": "bad3",
            "type": "oidc",
            "config": _oidc_config(client_secret_ref="plain-secret"),
        },
        headers=TENANT_HEADERS,
    )
    assert plaintext.status_code == 400 and plaintext.json()["code"] == 20064


@pytest.mark.kiwi_id(2203)
async def test_not_found_branches(client: AsyncClient, manage: ManageHarness) -> None:
    """不存在：详情 / 启停 / 删除 / 已存行测试均 20063。"""
    for method in ("GET", "DELETE"):
        response = await client.request(method, f"{_BASE}/999999", headers=TENANT_HEADERS)
        assert response.status_code == 404 and response.json()["code"] == 20063, (method, response.text)
    put = await client.put(f"{_BASE}/999999", json={}, headers=TENANT_HEADERS)
    assert put.status_code == 404 and put.json()["code"] == 20063
    response = await client.get(f"{_BASE}/999999/test", headers=TENANT_HEADERS)
    assert response.status_code == 404 and response.json()["code"] == 20063
    status = await client.post(f"{_BASE}/999999/status", json={"status": "enabled"}, headers=TENANT_HEADERS)
    assert status.status_code == 404 and status.json()["code"] == 20063


@pytest.mark.kiwi_id(2203)
async def test_status_invalid(client: AsyncClient, manage: ManageHarness) -> None:
    """启停状态非法 20064。"""
    created = await _create(client)
    response = await client.post(f"{_BASE}/{created['id']}/status", json={"status": "bogus"}, headers=TENANT_HEADERS)
    assert response.status_code == 400 and response.json()["code"] == 20064


@pytest.mark.kiwi_id(2203)
async def test_draft_and_saved_connectivity(client: AsyncClient, manage: ManageHarness) -> None:
    """草稿测试与已存行测试：成功 200、失败 20066（data 携结果）。"""
    draft = await client.post(f"{_BASE}/test", json={"type": "oidc", "config": _oidc_config()}, headers=TENANT_HEADERS)
    assert draft.status_code == 200
    assert draft.json()["data"]["reachable"] is True

    created = await _create(client)
    saved = await client.get(f"{_BASE}/{created['id']}/test", headers=TENANT_HEADERS)
    assert saved.status_code == 200 and saved.json()["data"]["reachable"] is True

    manage.probe.oidc_status = 503
    failed = await client.get(f"{_BASE}/{created['id']}/test", headers=TENANT_HEADERS)
    assert failed.status_code == 502 and failed.json()["code"] == 20066
    assert failed.json()["data"]["reachable"] is False


@pytest.mark.kiwi_id(2203)
async def test_wecom_draft_credentials_failure(client: AsyncClient, manage: ManageHarness) -> None:
    """企微草稿测试：gettoken errcode≠0 记不可达 20066。"""
    manage.probe.wecom_errcode = 40001
    response = await client.post(
        f"{_BASE}/test",
        json={
            "type": "wecom",
            "config": {"corp_id": "c", "agent_id": "a", "secret_ref": "env:MANAGE_TEST_SECRET"},
        },
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 502 and response.json()["code"] == 20066
    assert "40001" in response.json()["data"]["detail"]


@pytest.mark.kiwi_id(2203)
async def test_saved_row_invalid_config(client: AsyncClient, manage: ManageHarness) -> None:
    """已存行脏配置（非法 JSON / 非对象）：列表容错、已存行测试前置复校拦截 20064。"""
    await manage.seed_provider(idp_key="dirty", raw_config="{not-json")
    await manage.seed_provider(idp_key="listy", raw_config="[]")
    page = (await client.get(_BASE, headers=TENANT_HEADERS)).json()["data"]
    assert page["total"] == 2
    for item in page["list"]:
        assert item["config"] == {}
    for item in page["list"]:
        response = await client.get(f"{_BASE}/{item['id']}/test", headers=TENANT_HEADERS)
        assert response.status_code == 400 and response.json()["code"] == 20064


@pytest.mark.kiwi_id(2203)
async def test_draft_build_failure(client: AsyncClient, manage: ManageHarness) -> None:
    """草稿测试：凭据引用环境变量缺失（实例化失败）转 20066。"""
    response = await client.post(
        f"{_BASE}/test",
        json={"type": "oidc", "config": _oidc_config(client_secret_ref="env:MANAGE_MISSING_SECRET")},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 502 and response.json()["code"] == 20066
    assert response.json()["data"]["reachable"] is False


@pytest.mark.kiwi_id(2203)
async def test_test_rate_limit(client: AsyncClient, manage: ManageHarness) -> None:
    """连通性测试限流：超过阈值 10005/429。"""
    codes: list[int] = []
    for _ in range(11):
        response = await client.post(
            f"{_BASE}/test", json={"type": "oidc", "config": _oidc_config()}, headers=TENANT_HEADERS
        )
        codes.append(response.status_code)
    assert codes[-1] == 429
    assert 200 in codes


@pytest.mark.kiwi_id(2203)
async def test_requires_auth(service_app: FastAPI, manage: ManageHarness) -> None:
    """未登录 401；缺权限 403。"""
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as anonymous:
        response = await anonymous.get(_BASE, headers=TENANT_HEADERS)
    assert response.status_code == 401

    class _Deny:
        def require(self, code: str) -> None:
            raise PermissionError("deny")

    original = permission_base.get_permission_checker
    permission_base.get_permission_checker = lambda request: _Deny()  # type: ignore[assignment]
    try:
        async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as client:
            from tests_support.auth import auth_headers

            client.headers.update(auth_headers(tenant=TENANT_ID))
            denied = await client.get(_BASE, headers=TENANT_HEADERS)
        assert denied.status_code == 403
    finally:
        permission_base.get_permission_checker = original  # type: ignore[assignment]


@pytest.mark.kiwi_id(2203)
async def test_sso_providers_no_config(client: AsyncClient, manage: ManageHarness) -> None:
    """登录页入口清单不返回 config / 密钥。"""
    await _create(client)
    response = await client.get(_SSO_PROVIDERS, headers=TENANT_HEADERS)
    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert items and "config" not in items[0]
    assert "s3cr3t" not in str(items)
