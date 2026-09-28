"""OIDC Discovery / JWKS 端点测试（Kiwi 2202）。"""

import pytest
from httpx import AsyncClient

from .conftest import OidcHarness
from .helpers import ISSUER, TENANT_HEADERS


@pytest.mark.kiwi_id(2202)
async def test_discovery_document(client: AsyncClient, oidc: OidcHarness) -> None:
    """Discovery：200 且标准字段齐全、issuer 与端点前缀一致。"""
    response = await client.get("/api/v1/oidc/.well-known/openid-configuration", headers=TENANT_HEADERS)
    assert response.status_code == 200
    doc = response.json()
    assert doc["issuer"] == ISSUER
    assert doc["authorization_endpoint"] == f"{ISSUER}/authorize"
    assert doc["token_endpoint"] == f"{ISSUER}/token"
    assert doc["userinfo_endpoint"] == f"{ISSUER}/userinfo"
    assert doc["jwks_uri"] == f"{ISSUER}/jwks"
    assert doc["response_types_supported"] == ["code"]
    assert doc["grant_types_supported"] == ["authorization_code"]
    assert doc["code_challenge_methods_supported"] == ["S256"]


@pytest.mark.kiwi_id(2202)
async def test_discovery_with_tenant_param(client: AsyncClient, oidc: OidcHarness) -> None:
    """Discovery：`tenant` 参数回落分支（无租户头）。"""
    response = await client.get("/api/v1/oidc/.well-known/openid-configuration", params={"tenant_code": "demo"})
    assert response.status_code == 200
    assert response.json()["issuer"] == ISSUER


@pytest.mark.kiwi_id(2202)
async def test_jwks_publishes_user_token_keys(client: AsyncClient, oidc: OidcHarness) -> None:
    """JWKS：发布 `usr-` 前缀公钥（与用户令牌密钥同源）。"""
    response = await client.get("/api/v1/oidc/jwks", headers=TENANT_HEADERS)
    assert response.status_code == 200
    keys = response.json()["keys"]
    assert keys
    assert all(str(key["kid"]).startswith("usr-") for key in keys)
