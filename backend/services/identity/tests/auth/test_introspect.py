"""网关认证内部端点测试（Kiwi 2181）：公开路径 / 校验通过换发网关服务 JWT / 失败语义。

以 stub 校验器 / 真实签发者覆盖依赖，隔离外部 IdP；真实用户令牌端到端见 mjbk 冒烟。
"""

import asyncio
from collections.abc import Mapping

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from joserfc.jwk import RSAKey

from bms_core.api.deps import get_service_token_issuer, get_token_verifier
from bms_core.application import service_lifespan
from bms_core.core.exceptions import AuthError, ConfigError, ServiceUnavailableError
from bms_core.idp.base import IdentityClaims
from bms_core.oauth.base import OAuthToken
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.token import TOKEN_AUDIENCE_API, BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken
from bms_identity.main import ApplicationFactory

_INTROSPECT = "/api/v1/auth/introspect"


def _issuer() -> JwtServiceTokenIssuer:
    """构造带私钥的服务 JWT 签发者（RS256）。

    Returns:
        JwtServiceTokenIssuer: 签发者。
    """
    key = RSAKey.generate_key(2048, private=True)
    return JwtServiceTokenIssuer(
        issuer="bms",
        keys=[
            TokenKey(
                kid="k1",
                algorithm="RS256",
                public_key=key.as_pem(private=False).decode(),
                private_key=key.as_pem(private=True).decode(),
            )
        ],
        active_kid="k1",
    )


class _StubVerifier(BaseTokenVerifier):
    """占位校验器：按注入结果返回声明或抛错（隔离外部 IdP）。"""

    plugin_name = "stub"

    def __init__(self, *, result: VerifiedToken | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.audiences: list[str] = []

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """记录期望受众并返回注入结果 / 抛注入异常。"""
        self.audiences.append(audience)
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FailingIssuer(BaseServiceTokenIssuer):
    """占位签发者：签发即抛 `ConfigError`（模拟未配置签名私钥）。"""

    plugin_name = "failing"

    async def issue(self, spec: ServiceTokenSpec) -> OAuthToken:
        """恒定抛错。"""
        del spec
        raise ConfigError("未配置签名私钥")

    def jwks(self) -> Mapping[str, object]:
        """空 JWKS。"""
        return {"keys": []}

    def verify(self, token: str) -> IdentityClaims:
        """占位不验签（不参与本用例）。"""
        raise ConfigError(token)


async def _request(
    *,
    verifier: BaseTokenVerifier,
    issuer: BaseServiceTokenIssuer,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str]]:
    """构造应用并经依赖覆盖发起一次 introspect 请求。

    Args:
        verifier: 注入的统一校验器。
        issuer: 注入的服务 JWT 签发者。
        headers: 请求头。

    Returns:
        tuple[int, dict[str, str]]: 状态码与响应头。
    """
    app: FastAPI = ApplicationFactory().create(None)
    async with service_lifespan(app):
        app.dependency_overrides[get_token_verifier] = lambda: verifier
        app.dependency_overrides[get_service_token_issuer] = lambda: issuer
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(_INTROSPECT, headers=headers or {})
        return response.status_code, dict(response.headers)


def test_public_path_without_token_passes() -> None:
    """公开路径免认证：200 且无身份头 / 无 Authorization。"""
    status, headers = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_issuer(),
            headers={"X-Forwarded-Uri": "/api/identity/v1/auth/login"},
        )
    )
    assert status == 200
    assert "x-user-subject" not in headers
    assert "authorization" not in headers


def test_public_path_prefix_match_passes() -> None:
    """公开路径前缀匹配：验证码子路径免认证。"""
    status, _ = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_issuer(),
            headers={"X-Forwarded-Uri": "/api/identity/v1/captcha/abc?reload=1"},
        )
    )
    assert status == 200


def test_protected_path_without_forwarded_uri_uses_request_path() -> None:
    """无 `X-Forwarded-Uri` 时取请求路径，非公开且缺 token → 401。"""
    status, _ = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_issuer(),
        )
    )
    assert status == 401


def test_protected_path_with_minimal_claims_omits_optional_headers() -> None:
    """无租户 / scope 声明时不返回对应身份头（可选头分支）。"""
    status, headers = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_issuer(),
            headers={"Authorization": "Bearer user-token", "X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 200
    assert headers["x-user-subject"] == "u-1"
    assert "x-tenant-id" not in headers
    assert "x-user-scopes" not in headers


def test_protected_path_with_valid_token_issues_gateway_token() -> None:
    """受保护路径：校验通过后返回契约身份头 + 网关服务 JWT（可验签）。"""
    issuer = _issuer()
    verifier = _StubVerifier(result=VerifiedToken(subject="u-1", tenant="acme", scopes=("user:read", "user:write")))
    status, headers = asyncio.run(
        _request(
            verifier=verifier,
            issuer=issuer,
            headers={"Authorization": "Bearer user-token", "X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 200
    assert verifier.audiences == [TOKEN_AUDIENCE_API]
    assert headers["x-user-subject"] == "u-1"
    assert headers["x-tenant-id"] == "acme"
    assert headers["x-user-scopes"] == "user:read,user:write"
    claims = issuer.verify(headers["authorization"].removeprefix("Bearer "))
    assert claims.subject == "gateway"
    assert claims.payload["tenant"] == "acme"


def test_protected_path_without_token_is_unauthorized() -> None:
    """受保护路径缺 token → 401 + WWW-Authenticate。"""
    status, headers = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_issuer(),
            headers={"X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 401
    assert "www-authenticate" in headers


def test_protected_path_with_invalid_token_is_unauthorized() -> None:
    """受保护路径 token 校验失败（AuthError）→ 401。"""
    status, _ = asyncio.run(
        _request(
            verifier=_StubVerifier(error=AuthError("bad token")),
            issuer=_issuer(),
            headers={"Authorization": "Bearer bad", "X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 401


def test_protected_path_with_idp_unavailable_is_unavailable() -> None:
    """IdP JWKS 不可达（ServiceUnavailableError）→ 503。"""
    status, _ = asyncio.run(
        _request(
            verifier=_StubVerifier(error=ServiceUnavailableError("jwks down")),
            issuer=_issuer(),
            headers={"Authorization": "Bearer x", "X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 503


def test_issuance_failure_is_unavailable() -> None:
    """签发不可用（ConfigError，如未配置私钥）→ 503（fail-closed）。"""
    status, _ = asyncio.run(
        _request(
            verifier=_StubVerifier(result=VerifiedToken(subject="u-1")),
            issuer=_FailingIssuer(),
            headers={"Authorization": "Bearer user-token", "X-Forwarded-Uri": "/api/platform/v1/users"},
        )
    )
    assert status == 503
