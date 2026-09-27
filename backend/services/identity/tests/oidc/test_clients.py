"""客户端注册与管理接口测试（Kiwi 2202）。"""

import pytest
from httpx import AsyncClient

from .conftest import OidcHarness
from .helpers import TENANT_HEADERS, authorize_code, pkce

_CLIENTS = "/api/v1/open/clients"


async def _create(client: AsyncClient, **overrides: object) -> dict[str, object]:
    """调注册接口创建客户端。

    Args:
        client: 测试客户端。
        **overrides: 覆盖请求体字段。

    Returns:
        dict[str, object]: 响应 data。
    """
    body: dict[str, object] = {
        "name": "RP App",
        "redirect_uris": ["http://rp.test/created"],
        "grant_types": ["authorization_code"],
        "scopes": ["openid", "profile"],
    }
    body.update(overrides)
    response = await client.post(_CLIENTS, json=body, headers=TENANT_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.mark.kiwi_id(2202)
async def test_create_and_use_client(client: AsyncClient, oidc: OidcHarness) -> None:
    """注册返回 client_id + 明文 secret 一次，并可用于完整换码。"""
    created = await _create(client)
    client_id = str(created["client_id"])
    secret = str(created["client_secret"])
    assert client_id.startswith("bms_")
    assert secret
    verifier, challenge = pkce()
    code, _ = await authorize_code(
        client, client_id=client_id, redirect_uri="http://rp.test/created", code_challenge=challenge
    )
    token = await client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://rp.test/created",
            "code_verifier": verifier,
        },
        auth=(client_id, secret),
        headers=TENANT_HEADERS,
    )
    assert token.status_code == 200, token.text


@pytest.mark.kiwi_id(2202)
async def test_list_and_detail_never_expose_secret(client: AsyncClient, oidc: OidcHarness) -> None:
    """列表 / 详情不含 secret 与哈希。"""
    created = await _create(client)
    listing = await client.get(_CLIENTS, headers=TENANT_HEADERS)
    assert listing.status_code == 200
    page = listing.json()["data"]
    assert page["total"] == 1
    item = page["list"][0]
    assert "client_secret" not in item
    assert "client_secret_hash" not in item
    assert item["client_id"] == created["client_id"]
    assert item["redirect_uris"] == ["http://rp.test/created"]

    detail = await client.get(f"{_CLIENTS}/{item['id']}", headers=TENANT_HEADERS)
    assert detail.status_code == 200
    assert "client_secret" not in detail.json()["data"]


@pytest.mark.kiwi_id(2202)
async def test_status_disable_blocks_authorize(client: AsyncClient, oidc: OidcHarness) -> None:
    """停用后授权被拒（400 标准错误）。"""
    created = await _create(client)
    page = (await client.get(_CLIENTS, headers=TENANT_HEADERS)).json()["data"]
    item_id = page["list"][0]["id"]
    disabled = await client.post(f"{_CLIENTS}/{item_id}/status", json={"status": "disabled"}, headers=TENANT_HEADERS)
    assert disabled.status_code == 200
    response = await client.get(
        "/api/v1/oidc/authorize",
        params={
            "response_type": "code",
            "client_id": str(created["client_id"]),
            "redirect_uri": "http://rp.test/created",
            "scope": "openid",
        },
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 400


@pytest.mark.kiwi_id(2202)
async def test_reset_secret_invalidates_old(client: AsyncClient, oidc: OidcHarness) -> None:
    """重置密钥：旧密钥失效、新密钥可换码。"""
    created = await _create(client)
    client_id = str(created["client_id"])
    old_secret = str(created["client_secret"])
    page = (await client.get(_CLIENTS, headers=TENANT_HEADERS)).json()["data"]
    item_id = page["list"][0]["id"]
    reset = await client.post(f"{_CLIENTS}/{item_id}/reset-secret", headers=TENANT_HEADERS)
    assert reset.status_code == 200
    new_secret = reset.json()["data"]["client_secret"]
    assert new_secret != old_secret

    verifier, challenge = pkce()
    code, _ = await authorize_code(
        client, client_id=client_id, redirect_uri="http://rp.test/created", code_challenge=challenge
    )
    old_try = await client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://rp.test/created",
            "code_verifier": verifier,
        },
        auth=(client_id, old_secret),
        headers=TENANT_HEADERS,
    )
    assert old_try.status_code == 401

    verifier2, challenge2 = pkce()
    code2, _ = await authorize_code(
        client, client_id=client_id, redirect_uri="http://rp.test/created", code_challenge=challenge2
    )
    new_try = await client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": code2,
            "redirect_uri": "http://rp.test/created",
            "code_verifier": verifier2,
        },
        auth=(client_id, new_secret),
        headers=TENANT_HEADERS,
    )
    assert new_try.status_code == 200


@pytest.mark.kiwi_id(2202)
async def test_create_public_client_and_reset_rejected(client: AsyncClient, oidc: OidcHarness) -> None:
    """公共客户端：secret 为空；重置密钥被拒（80112）。"""
    created = await _create(client, public=True, redirect_uris=["http://rp.test/pub"])
    assert created["client_secret"] == ""
    page = (await client.get(_CLIENTS, headers=TENANT_HEADERS)).json()["data"]
    item_id = page["list"][0]["id"]
    reset = await client.post(f"{_CLIENTS}/{item_id}/reset-secret", headers=TENANT_HEADERS)
    assert reset.status_code == 400
    assert reset.json()["code"] == 80112


@pytest.mark.kiwi_id(2202)
async def test_create_invalid_fields(client: AsyncClient, oidc: OidcHarness) -> None:
    """非法字段：80112/400（授权类型非法、回调非 http(s)、缺回调）。"""
    bad_grant = await client.post(
        _CLIENTS,
        json={"name": "X", "redirect_uris": ["http://x/cb"], "grant_types": ["bogus"], "scopes": ["openid"]},
        headers=TENANT_HEADERS,
    )
    assert bad_grant.status_code == 400
    assert bad_grant.json()["code"] == 80112

    bad_scheme = await client.post(
        _CLIENTS,
        json={
            "name": "X",
            "redirect_uris": ["ftp://x/cb"],
            "grant_types": ["authorization_code"],
            "scopes": ["openid"],
        },
        headers=TENANT_HEADERS,
    )
    assert bad_scheme.status_code == 400
    assert bad_scheme.json()["code"] == 80112

    no_redirect = await client.post(
        _CLIENTS,
        json={"name": "X", "redirect_uris": [], "grant_types": ["authorization_code"], "scopes": ["openid"]},
        headers=TENANT_HEADERS,
    )
    assert no_redirect.status_code == 400
    assert no_redirect.json()["code"] == 80112


@pytest.mark.kiwi_id(2202)
async def test_get_missing_client(client: AsyncClient, oidc: OidcHarness) -> None:
    """不存在客户端：80111/404。"""
    response = await client.get(f"{_CLIENTS}/999999", headers=TENANT_HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == 80111


@pytest.mark.kiwi_id(2202)
async def test_list_filters(client: AsyncClient, oidc: OidcHarness) -> None:
    """列表筛选：status 精确 + name 模糊。"""
    await _create(client, name="Alpha One", redirect_uris=["http://rp.test/a"])
    await _create(client, name="Beta Two", redirect_uris=["http://rp.test/b"])
    both = await client.get(_CLIENTS, params={"name": "Alpha"}, headers=TENANT_HEADERS)
    assert both.json()["data"]["total"] == 1
    enabled = await client.get(_CLIENTS, params={"status": "enabled"}, headers=TENANT_HEADERS)
    assert enabled.json()["data"]["total"] == 2
    none = await client.get(_CLIENTS, params={"status": "disabled"}, headers=TENANT_HEADERS)
    assert none.json()["data"]["total"] == 0


@pytest.mark.kiwi_id(2202)
async def test_status_invalid_and_missing(client: AsyncClient, oidc: OidcHarness) -> None:
    """启停：非法状态 80112；不存在 80111。"""
    created = await _create(client)
    page = (await client.get(_CLIENTS, headers=TENANT_HEADERS)).json()["data"]
    item_id = page["list"][0]["id"]
    invalid = await client.post(f"{_CLIENTS}/{item_id}/status", json={"status": "bogus"}, headers=TENANT_HEADERS)
    assert invalid.status_code == 400
    assert invalid.json()["code"] == 80112
    missing = await client.post(f"{_CLIENTS}/999999/status", json={"status": "disabled"}, headers=TENANT_HEADERS)
    assert missing.status_code == 404
    assert missing.json()["code"] == 80111
    assert created["client_id"]


@pytest.mark.kiwi_id(2202)
async def test_reset_missing_client(client: AsyncClient, oidc: OidcHarness) -> None:
    """重置密钥：不存在客户端 80111。"""
    response = await client.post(f"{_CLIENTS}/999999/reset-secret", headers=TENANT_HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == 80111


@pytest.mark.kiwi_id(2202)
async def test_create_invalid_scopes(client: AsyncClient, oidc: OidcHarness) -> None:
    """scope 空 / 缺 openid：80112。"""
    empty = await client.post(
        _CLIENTS,
        json={"name": "X", "redirect_uris": ["http://x/cb"], "grant_types": ["authorization_code"], "scopes": []},
        headers=TENANT_HEADERS,
    )
    assert empty.status_code == 400
    assert empty.json()["code"] == 80112
    no_openid = await client.post(
        _CLIENTS,
        json={
            "name": "X",
            "redirect_uris": ["http://x/cb"],
            "grant_types": ["authorization_code"],
            "scopes": ["profile"],
        },
        headers=TENANT_HEADERS,
    )
    assert no_openid.status_code == 400
    assert no_openid.json()["code"] == 80112
