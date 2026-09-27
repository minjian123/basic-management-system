"""OIDC 令牌端点测试（Kiwi 2202）。"""

import pytest
from httpx import AsyncClient
from joserfc import jwt
from joserfc.jwk import KeySet

from .conftest import OidcHarness
from .helpers import CLIENT_ID, CLIENT_SECRET, ISSUER, REDIRECT_URI, TENANT_HEADERS, authorize_code, pkce

_TOKEN = "/api/v1/oidc/token"


async def _issue_code(client: AsyncClient, *, public: bool = False) -> tuple[str, str]:
    """发起授权并返回 (code, code_verifier)。

    Args:
        client: 测试客户端。
        public: 是否公共客户端（强制 PKCE）。

    Returns:
        tuple[str, str]: (授权码, code_verifier)。
    """
    verifier, challenge = pkce()
    code, _ = await authorize_code(client, code_challenge=challenge, code_challenge_method="S256")
    return code, verifier


@pytest.mark.kiwi_id(2202)
async def test_token_happy_path_basic(client: AsyncClient, oidc: OidcHarness) -> None:
    """授权码换码（basic）：返回 id_token + access_token，无 refresh_token。"""
    await oidc.seed_client()
    code, verifier = await _issue_code(client)
    response = await client.post(
        _TOKEN,
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
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 300
    assert body["scope"] == "openid"
    assert body["id_token"]
    assert "refresh_token" not in body

    jwks = (await client.get("/api/v1/oidc/jwks", headers=TENANT_HEADERS)).json()
    id_claims = jwt.decode(body["id_token"], KeySet.import_key_set(jwks)).claims
    assert id_claims["iss"] == ISSUER
    assert id_claims["aud"] == CLIENT_ID
    assert id_claims["sub"] == "1001"
    assert id_claims["nonce"] == "nonce-1"
    assert id_claims["preferred_username"] == "alice"


@pytest.mark.kiwi_id(2202)
async def test_token_client_secret_post(client: AsyncClient, oidc: OidcHarness) -> None:
    """授权码换码（表单 client_secret_post）：成功。"""
    await oidc.seed_client()
    code, verifier = await _issue_code(client)
    response = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200


@pytest.mark.kiwi_id(2202)
async def test_token_public_client_pkce(client: AsyncClient, oidc: OidcHarness) -> None:
    """公共客户端（无密钥）+ PKCE：成功。"""
    await oidc.seed_client(public=True)
    code, verifier = await _issue_code(client, public=True)
    response = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": CLIENT_ID,
        },
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 200


@pytest.mark.kiwi_id(2202)
async def test_token_code_replay(client: AsyncClient, oidc: OidcHarness) -> None:
    """授权码重放：二次换码 invalid_grant。"""
    await oidc.seed_client()
    code, verifier = await _issue_code(client)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    first = await client.post(_TOKEN, data=data, auth=(CLIENT_ID, CLIENT_SECRET), headers=TENANT_HEADERS)
    assert first.status_code == 200
    second = await client.post(_TOKEN, data=data, auth=(CLIENT_ID, CLIENT_SECRET), headers=TENANT_HEADERS)
    assert second.status_code == 400
    assert second.json()["error"] == "invalid_grant"


@pytest.mark.kiwi_id(2202)
async def test_token_redirect_mismatch(client: AsyncClient, oidc: OidcHarness) -> None:
    """redirect_uri 与授权时不一致：invalid_grant。"""
    await oidc.seed_client()
    code, verifier = await _issue_code(client)
    response = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://rp.test/other",
            "code_verifier": verifier,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


@pytest.mark.kiwi_id(2202)
async def test_token_pkce_mismatch(client: AsyncClient, oidc: OidcHarness) -> None:
    """PKCE verifier 不符：invalid_grant。"""
    await oidc.seed_client()
    code, _ = await _issue_code(client)
    response = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": "wrong-verifier",
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


@pytest.mark.kiwi_id(2202)
async def test_token_unknown_client_and_bad_secret(client: AsyncClient, oidc: OidcHarness) -> None:
    """未知客户端 / 错密钥：401 invalid_client。"""
    await oidc.seed_client()
    code, verifier = await _issue_code(client)
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    unknown = await client.post(_TOKEN, data=data, auth=("ghost", "x"), headers=TENANT_HEADERS)
    assert unknown.status_code == 401
    assert unknown.json()["error"] == "invalid_client"

    code2, verifier2 = await _issue_code(client)
    bad = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code2,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier2,
        },
        auth=(CLIENT_ID, "wrong-secret"),
        headers=TENANT_HEADERS,
    )
    assert bad.status_code == 401
    assert bad.json()["error"] == "invalid_client"


@pytest.mark.kiwi_id(2202)
async def test_token_missing_params_and_user_missing(client: AsyncClient, oidc: OidcHarness) -> None:
    """缺 code / 用户不存在：invalid_grant。"""
    await oidc.seed_client()
    missing = await client.post(
        _TOKEN,
        data={"grant_type": "authorization_code", "redirect_uri": REDIRECT_URI},
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert missing.status_code == 400
    assert missing.json()["error"] == "invalid_grant"

    code, verifier = await _issue_code(client)
    oidc.org.remove_user(1001)
    gone = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers=TENANT_HEADERS,
    )
    assert gone.status_code == 400
    assert gone.json()["error"] == "invalid_grant"


@pytest.mark.kiwi_id(2202)
async def test_token_public_client_rejects_secret(client: AsyncClient, oidc: OidcHarness) -> None:
    """公共客户端携带密钥：invalid_client。"""
    await oidc.seed_client(public=True)
    code, verifier = await _issue_code(client, public=True)
    response = await client.post(
        _TOKEN,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": CLIENT_ID,
            "client_secret": "should-not-send",
        },
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_client"


@pytest.mark.kiwi_id(2202)
async def test_token_unsupported_grant(client: AsyncClient, oidc: OidcHarness) -> None:
    """非授权码 grant_type：unsupported_grant_type。"""
    await oidc.seed_client()
    response = await client.post(
        _TOKEN,
        data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        headers=TENANT_HEADERS,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "unsupported_grant_type"
