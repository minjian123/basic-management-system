"""双类 JWT · JWKS 公开端点测试（Kiwi 2180 / 2193）：路由 / 合并公钥集 / 冲突 fail-closed / 空集 / 豁免路径。

`GET /.well-known/jwks.json` 由 identity 服务宿主，同端点发布服务令牌与用户令牌公钥；无密钥时返回空集。
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from joserfc.jwk import RSAKey

from bms_core.application import service_lifespan
from bms_core.db.tenant import DEFAULT_EXEMPT_PATHS
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.user_jwt import JwtUserTokenIssuer
from bms_identity.main import ApplicationFactory


def _service_issuer(kid: str = "svc-k1") -> JwtServiceTokenIssuer:
    """构造带公钥的服务 JWT 签发者。

    Args:
        kid: 密钥标识。

    Returns:
        JwtServiceTokenIssuer: 签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtServiceTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid=kid,
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid=kid,
    )


def _user_issuer(kid: str = "usr-k1") -> JwtUserTokenIssuer:
    """构造带公钥的用户令牌签发者。

    Args:
        kid: 密钥标识（须带 `usr-` 前缀）。

    Returns:
        JwtUserTokenIssuer: 签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtUserTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid=kid,
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid=kid,
        access_ttl=1800,
        refresh_ttl=1209600,
    )


@pytest.mark.kiwi_id(2180)
def test_jwks_path_is_tenant_exempt() -> None:
    """JWKS 端点纳入租户解析豁免缺省集。"""
    assert "/.well-known/jwks.json" in DEFAULT_EXEMPT_PATHS


@pytest.mark.kiwi_id(2193)
def test_jwks_route_merges_service_and_user_keys() -> None:
    """路由合并发布两类公钥（服务 `svc-*` + 用户 `usr-*`），只含公钥、按 kid 排序，无统一响应包体。"""

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            app.state.service_token = _service_issuer()
            app.state.user_token = _user_issuer()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/.well-known/jwks.json")
            assert response.status_code == 200
            payload = response.json()
            assert list(payload.keys()) == ["keys"]
            assert [item["kid"] for item in payload["keys"]] == ["svc-k1", "usr-k1"]
            assert all(item["alg"] == "RS256" for item in payload["keys"])
            assert all("d" not in item for item in payload["keys"])

    asyncio.run(_run())


@pytest.mark.kiwi_id(2193)
def test_jwks_route_conflict_is_unavailable() -> None:
    """两域 kid 冲突（同 kid 不同用途）→ 503（fail-closed，不发布有歧义的键集）。"""

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            app.state.service_token = _service_issuer(kid="usr-k1")
            app.state.user_token = _user_issuer(kid="usr-k1")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/.well-known/jwks.json")
            assert response.status_code == 503

    asyncio.run(_run())


@pytest.mark.kiwi_id(2180)
def test_jwks_route_empty_without_keys() -> None:
    """无密钥时返回空公钥集（不失败）。"""

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/.well-known/jwks.json")
            assert response.status_code == 200
            assert response.json() == {"keys": []}

    asyncio.run(_run())


@pytest.mark.kiwi_id(2193)
def test_dependency_providers_resolve() -> None:
    """依赖提供者：路由经服务 / 用户签发者与统一校验器取到装配实例。"""
    from typing import Annotated

    from fastapi import Depends

    from bms_core.api.deps import get_service_token_issuer, get_token_verifier, get_user_token_issuer
    from bms_core.oauth.token import BaseServiceTokenIssuer
    from bms_core.oauth.user_token import BaseUserTokenIssuer
    from bms_core.oauth.verify import BaseTokenVerifier

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):

            @app.get("/token-probe")
            async def probe(  # pyright: ignore[reportUnusedFunction]
                issuer: Annotated[BaseServiceTokenIssuer, Depends(get_service_token_issuer)],
                user_issuer: Annotated[BaseUserTokenIssuer, Depends(get_user_token_issuer)],
                verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
            ) -> dict[str, str]:
                return {
                    "issuer": type(issuer).__name__,
                    "user_issuer": type(user_issuer).__name__,
                    "verifier": verifier.key,
                }

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/token-probe")
            assert response.status_code == 200
            assert response.json() == {
                "issuer": "JwtServiceTokenIssuer",
                "user_issuer": "JwtUserTokenIssuer",
                "verifier": "token_verifier",
            }

    asyncio.run(_run())
