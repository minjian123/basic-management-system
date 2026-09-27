"""OIDC userinfo 端点测试（Kiwi 2202）。"""

import time

import pytest
from httpx import AsyncClient
from joserfc import jwt
from joserfc.jwk import RSAKey

from tests_support.auth import TEST_KID, _key_pems  # pyright: ignore[reportPrivateUsage]

from .conftest import OidcHarness
from .helpers import CLIENT_ID, CLIENT_SECRET, ISSUER, REDIRECT_URI, TENANT_HEADERS, authorize_code, pkce

_USERINFO = "/api/v1/oidc/userinfo"


async def _access_token(client: AsyncClient) -> str:
    """完成一次授权码流程并返回 access token。

    Args:
        client: 测试客户端。

    Returns:
        str: IdP access token。
    """
    verifier, challenge = pkce()
    code, _ = await authorize_code(client, code_challenge=challenge, code_challenge_method="S256")
    response = await client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.mark.kiwi_id(2202)
async def test_userinfo_happy_path(client: AsyncClient, oidc: OidcHarness) -> None:
    """userinfo：Bearer access token → sub / preferred_username / name。"""
    await oidc.seed_client()
    token = await _access_token(client)
    response = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body == {"sub": "1001", "preferred_username": "alice", "name": "Alice"}


@pytest.mark.kiwi_id(2202)
async def test_userinfo_missing_or_invalid_token(client: AsyncClient, oidc: OidcHarness) -> None:
    """缺 / 非法令牌：401。"""
    await oidc.seed_client()
    missing = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": ""})
    assert missing.status_code == 401
    invalid = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": "Bearer nope"})
    assert invalid.status_code == 401


@pytest.mark.kiwi_id(2202)
async def test_userinfo_cross_tenant_rejected(client: AsyncClient, oidc: OidcHarness) -> None:
    """access token 租户与请求租户不符：401。"""
    await oidc.seed_client()
    _, private_key = _key_pems()
    now = int(time.time())
    forged = jwt.encode(
        {"alg": "RS256", "kid": TEST_KID},
        {
            "iss": ISSUER,
            "sub": "1001",
            "aud": "userinfo",
            "typ": "idp_access",
            "tenant_id": "other",
            "jti": "j1",
            "iat": now,
            "exp": now + 300,
        },
        RSAKey.import_key(private_key),
    )
    response = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


@pytest.mark.kiwi_id(2202)
async def test_userinfo_user_missing_and_org_down(client: AsyncClient, oidc: OidcHarness) -> None:
    """用户不存在 / 停用 → 401；org 不可达 → 503。"""
    await oidc.seed_client()
    token = await _access_token(client)
    oidc.org.remove_user(1001)
    gone = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": f"Bearer {token}"})
    assert gone.status_code == 401

    oidc.org.set_user(1001, status="disabled")
    disabled = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": f"Bearer {token}"})
    assert disabled.status_code == 401

    oidc.org.set_user(1001, status="enabled")
    oidc.org.fail = True
    down = await client.get(_USERINFO, headers={**TENANT_HEADERS, "Authorization": f"Bearer {token}"})
    assert down.status_code == 503
