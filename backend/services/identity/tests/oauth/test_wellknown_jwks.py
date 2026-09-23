"""双类 JWT · JWKS 公开端点测试（Kiwi 2180）：路由 / 公钥集 / 空集 / 豁免路径。

`GET /.well-known/jwks.json` 由 identity 服务宿主；无密钥时返回空集，注入密钥后返回公钥集。
"""

import asyncio

from httpx import ASGITransport, AsyncClient
from joserfc.jwk import RSAKey

from bms_core.application import service_lifespan
from bms_core.db.tenant import DEFAULT_EXEMPT_PATHS
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_identity.main import ApplicationFactory


def _issuer(kid: str = "k1") -> JwtServiceTokenIssuer:
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


def test_jwks_path_is_tenant_exempt() -> None:
    """JWKS 端点纳入租户解析豁免缺省集。"""
    assert "/.well-known/jwks.json" in DEFAULT_EXEMPT_PATHS


def test_jwks_route_returns_public_keys() -> None:
    """路由返回标准 JWKS 文档（只含公钥），无统一响应包体。"""

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):
            app.state.service_token = _issuer()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/.well-known/jwks.json")
            assert response.status_code == 200
            payload = response.json()
            assert list(payload.keys()) == ["keys"]
            assert payload["keys"][0]["kid"] == "k1"
            assert payload["keys"][0]["alg"] == "RS256"
            assert "d" not in payload["keys"][0]

    asyncio.run(_run())


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


def test_dependency_providers_resolve() -> None:
    """依赖提供者：路由经 `get_service_token_issuer` / `get_token_verifier` 取到装配实例。"""
    from typing import Annotated

    from fastapi import Depends

    from bms_core.api.deps import get_service_token_issuer, get_token_verifier
    from bms_core.oauth.token import BaseServiceTokenIssuer
    from bms_core.oauth.verify import BaseTokenVerifier

    async def _run() -> None:
        app = ApplicationFactory().create(None)
        async with service_lifespan(app):

            @app.get("/token-probe")
            async def probe(  # pyright: ignore[reportUnusedFunction]
                issuer: Annotated[BaseServiceTokenIssuer, Depends(get_service_token_issuer)],
                verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
            ) -> dict[str, str]:
                return {"issuer": type(issuer).__name__, "verifier": verifier.key}

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/token-probe")
            assert response.status_code == 200
            assert response.json() == {"issuer": "JwtServiceTokenIssuer", "verifier": "token_verifier"}

    asyncio.run(_run())
