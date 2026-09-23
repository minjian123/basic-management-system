"""服务 JWT 边缘信任实现测试（Kiwi 2181）：验签信任 / 身份解析 / 缺失或无效拒绝 / 工厂拒空。

本机以 joserfc 生成密钥对，无需外部依赖；装配解析与旁路行为见 `test_edge.py` / `test_middleware.py`。
"""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import RSAKey

from bms_core.core.config import Settings
from bms_core.core.exceptions import PluginError
from bms_core.edge.headers import (
    SERVICE_IDENTITY_HEADER,
    TENANT_ID_HEADER,
    USER_ID_HEADER,
    USER_SCOPES_HEADER,
    USER_SUBJECT_HEADER,
)
from bms_core.edge.service_jwt import ServiceJwtEdgeTrust, ServiceJwtEdgeTrustFactory
from bms_core.oauth.jwt import JwtServiceTokenIssuer
from bms_core.oauth.keys import TokenKey
from bms_core.oauth.token import TOKEN_AUDIENCE_API, ServiceTokenSpec

pytestmark = pytest.mark.kiwi_id(2181)


def _issuer() -> tuple[JwtServiceTokenIssuer, RSAKey]:
    """构造真实服务 JWT 签发者（RS256）与底层密钥。

    Returns:
        tuple[JwtServiceTokenIssuer, RSAKey]: 签发者与签名密钥对象。
    """
    key = RSAKey.generate_key(2048, private=True)
    token_key = TokenKey(
        kid="k1",
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )
    return JwtServiceTokenIssuer(keys=[token_key], active_kid="k1"), key


def _issue(issuer: JwtServiceTokenIssuer, *, tenant: str | None = "acme") -> str:
    """签发一枚服务 JWT（网关服务身份）。

    Args:
        issuer: 服务 JWT 签发者。
        tenant: 租户编码。

    Returns:
        str: 紧凑 JWT。
    """
    spec = ServiceTokenSpec(service="gateway", scopes=("gateway",), tenant=tenant)
    return asyncio.run(issuer.issue(spec)).access_token


def test_service_jwt_trusts_valid_token_and_parses_identity() -> None:
    """有效服务 JWT → 信任；服务身份取 JWT `sub`，用户身份取身份头。"""
    issuer, _ = _issuer()
    guard = ServiceJwtEdgeTrust(issuer=issuer)
    decision = guard.evaluate(
        {
            "Authorization": f"Bearer {_issue(issuer)}",
            USER_ID_HEADER: "42",
            USER_SUBJECT_HEADER: "u-1",
            USER_SCOPES_HEADER: "user:read, user:write,, ",
            TENANT_ID_HEADER: "acme",
        }
    )
    assert decision.trusted is True
    identity = decision.identity
    assert identity is not None
    assert identity.user_id == 42
    assert identity.subject == "u-1"
    assert identity.service_identity == "gateway"
    assert identity.tenant_code == "acme"
    assert identity.scopes == ("user:read", "user:write")


def test_service_jwt_falls_back_to_token_tenant_claim() -> None:
    """身份头无租户时回落服务 JWT 的 `tenant` claim。"""
    issuer, _ = _issuer()
    guard = ServiceJwtEdgeTrust(issuer=issuer)
    decision = guard.evaluate({"Authorization": f"Bearer {_issue(issuer, tenant='beta')}"})
    assert decision.trusted is True
    assert decision.identity is not None
    assert decision.identity.tenant_code == "beta"
    assert decision.identity.service_identity == "gateway"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer "},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer not.a.jwt"},
    ],
)
def test_service_jwt_rejects_missing_or_invalid(headers: dict[str, str]) -> None:
    """缺失 / 非 Bearer / 非法令牌 → 不信任、无身份（不抛错）。"""
    issuer, _ = _issuer()
    decision = ServiceJwtEdgeTrust(issuer=issuer).evaluate(headers)
    assert decision.trusted is False
    assert decision.identity is None


def test_service_jwt_rejects_user_audience_token() -> None:
    """`aud` 隔离：同密钥签发的用户受众（`aud=api`）令牌以服务期望校验被拒。"""
    issuer, key = _issuer()
    user_token = joserfc_jwt.encode(
        {"alg": "RS256", "kid": "k1"},
        {"iss": "bms", "sub": "user-1", "aud": TOKEN_AUDIENCE_API, "exp": 4102444800},
        key,
    )
    decision = ServiceJwtEdgeTrust(issuer=issuer).evaluate({"Authorization": f"Bearer {user_token}"})
    assert decision.trusted is False
    assert decision.identity is None


def test_service_jwt_factory_rejects_empty_provider() -> None:
    """`[service_token].provider` 为空（占位）→ 拒绝装配（fail-closed）。"""
    settings = cast("Settings", SimpleNamespace(service_token=SimpleNamespace(provider="")))
    with pytest.raises(PluginError):
        ServiceJwtEdgeTrustFactory(settings).create()


def test_service_identity_header_constant_matches_parsing() -> None:
    """服务身份头为契约常量（与 edge.headers 单一来源一致）。"""
    assert SERVICE_IDENTITY_HEADER == "X-Service-Identity"
