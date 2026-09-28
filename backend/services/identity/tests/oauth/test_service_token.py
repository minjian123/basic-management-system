"""双类 JWT · 服务 JWT 自签测试（Kiwi 2180）：契约 / 签发 / JWKS / 轮换 / 配置 / 部署件护栏。

本机以 joserfc 生成密钥对，无需外部依赖；真机集成（真实 Keycloak 用户令牌）见 `test_token_verifier.py`
与任务测试记录。
"""

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.config import ServiceTokenSettings, Settings, TokenKeySettings
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.oauth.base import NULL_ACCESS_TOKEN, OAuthToken
from bms_core.oauth.jwt import JwtServiceTokenIssuer, JwtServiceTokenIssuerFactory
from bms_core.oauth.keys import ALLOWED_ALGORITHMS, TokenKey, build_jwks
from bms_core.oauth.null import NullServiceTokenIssuer
from bms_core.oauth.token import (
    DEFAULT_SERVICE_TOKEN_ISSUER,
    DEFAULT_SERVICE_TOKEN_TTL,
    SERVICE_TOKEN_TYPE,
    TOKEN_AUDIENCE_API,
    TOKEN_AUDIENCE_SERVICE,
    BaseServiceTokenIssuer,
    ServiceTokenSpec,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_REALM_FILE = _BACKEND_ROOT.parent / "deploy" / "keycloak" / "bms-realm.json"


def _rsa_key(kid: str = "k1") -> TokenKey:
    """生成 RSA 密钥 TokenKey（RS256）。

    Args:
        kid: 密钥标识。

    Returns:
        TokenKey: RSA 密钥。
    """
    key = RSAKey.generate_key(2048, private=True)
    return TokenKey(
        kid=kid,
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )


def _ec_key(kid: str = "e1") -> TokenKey:
    """生成 EC 密钥 TokenKey（ES256）。

    Args:
        kid: 密钥标识。

    Returns:
        TokenKey: EC 密钥。
    """
    key = ECKey.generate_key("P-256", private=True)
    return TokenKey(
        kid=kid,
        algorithm="ES256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )


@pytest.mark.kiwi_id(2180)
def test_constants_and_contract() -> None:
    """受众 / 类型 / 默认值常量与契约继承链。"""
    assert ALLOWED_ALGORITHMS == ("RS256", "ES256")
    assert TOKEN_AUDIENCE_API == "api"
    assert TOKEN_AUDIENCE_SERVICE == "service"
    assert SERVICE_TOKEN_TYPE == "service"
    assert DEFAULT_SERVICE_TOKEN_ISSUER == "bms"
    assert DEFAULT_SERVICE_TOKEN_TTL == 300
    assert BaseServiceTokenIssuer.key == BaseServiceTokenIssuer.plugin_key == "service_token"
    assert issubclass(JwtServiceTokenIssuer, BaseServiceTokenIssuer)
    assert issubclass(NullServiceTokenIssuer, BaseServiceTokenIssuer)
    spec = ServiceTokenSpec(service="platform")
    assert spec.scopes == () and spec.tenant is None and spec.ttl is None


@pytest.mark.kiwi_id(2180)
def test_token_key_validation() -> None:
    """密钥校验：算法白名单、公私钥齐备、导入与 JWK 输出。"""
    key = _rsa_key()
    assert key.can_sign is True
    jwk = key.public_jwk()
    assert jwk["kid"] == "k1" and jwk["alg"] == "RS256" and jwk["kty"] == "RSA"
    assert "d" not in jwk

    with pytest.raises(ConfigError):
        TokenKey(kid="bad", algorithm="HS256", public_key="x")
    with pytest.raises(ConfigError):
        TokenKey(kid="empty")
    with pytest.raises(ConfigError):
        TokenKey(kid="nopriv", public_key=key.public_key).signing_key()
    with pytest.raises(ConfigError):
        TokenKey(kid="nopub", private_key=key.private_key).verify_key()
    with pytest.raises(ConfigError):
        TokenKey(kid="badpem", public_key="not-a-pem").public_jwk()

    ec = _ec_key()
    assert ec.public_jwk()["kty"] == "EC"
    public_only = TokenKey(kid="p1", public_key=key.public_key)
    assert public_only.can_sign is False


@pytest.mark.kiwi_id(2180)
def test_build_jwks_only_public_sorted() -> None:
    """JWKS 文档只含公钥、按 kid 排序。"""
    keys = [_rsa_key("k2"), _rsa_key("k1")]
    jwks = build_jwks(keys)
    entries = cast("list[dict[str, object]]", jwks["keys"])
    assert [item["kid"] for item in entries] == ["k1", "k2"]
    assert all("d" not in item for item in entries)


@pytest.mark.kiwi_id(2180)
async def test_issue_and_verify_claims() -> None:
    """签发服务 JWT：固定 + 扩展 claims、`aud=service`、TTL 与 scope 回填、本地验签通过。"""
    issuer = JwtServiceTokenIssuer(issuer="bms", keys=[_rsa_key()], active_kid="k1")
    token = await issuer.issue(ServiceTokenSpec(service="platform", scopes=("user:read", "org:read"), tenant="acme"))
    assert isinstance(token, OAuthToken)
    assert token.expires_in == DEFAULT_SERVICE_TOKEN_TTL
    assert token.scopes == ("user:read", "org:read")

    claims = issuer.verify(token.access_token)
    assert claims.subject == "platform"
    assert claims.issuer == "bms"
    assert claims.audience == (TOKEN_AUDIENCE_SERVICE,)
    payload = dict(claims.payload)
    assert payload["typ"] == SERVICE_TOKEN_TYPE
    assert payload["service"] == "platform"
    assert payload["tenant"] == "acme"
    assert payload["scope"] == "user:read org:read"
    assert payload["jti"]
    assert claims.expires_at > claims.issued_at


@pytest.mark.kiwi_id(2180)
async def test_issue_ec_algorithm() -> None:
    """ES256 密钥可签发并通过本地验签。"""
    issuer = JwtServiceTokenIssuer(issuer="bms", keys=[_ec_key()], active_kid="e1")
    token = await issuer.issue(ServiceTokenSpec(service="org"))
    assert issuer.verify(token.access_token).subject == "org"


@pytest.mark.kiwi_id(2180)
async def test_verify_rejects_tampered_and_wrong_issuer() -> None:
    """篡改签名 / issuer 不符均抛认证错误。"""
    issuer = JwtServiceTokenIssuer(issuer="bms", keys=[_rsa_key()], active_kid="k1")
    token = (await issuer.issue(ServiceTokenSpec(service="platform"))).access_token

    with pytest.raises(AuthError):
        issuer.verify(token[:-3] + "abc")

    other = JwtServiceTokenIssuer(issuer="other", keys=[_rsa_key()], active_kid="k1")
    with pytest.raises(AuthError):
        other.verify(token)


@pytest.mark.kiwi_id(2180)
async def test_key_rotation_parallel_verification() -> None:
    """多密钥并行：新 kid 签发、旧 kid 票据在新 JWKS 下仍可验，淘汰后失效。"""
    old, new = _rsa_key("k1"), _rsa_key("k2")
    first = JwtServiceTokenIssuer(issuer="bms", keys=[old], active_kid="k1")
    old_token = (await first.issue(ServiceTokenSpec(service="platform"))).access_token

    rotated = JwtServiceTokenIssuer(issuer="bms", keys=[old, new], active_kid="k2")
    new_token = (await rotated.issue(ServiceTokenSpec(service="org"))).access_token
    assert rotated.verify(new_token).subject == "org"
    assert rotated.verify(old_token).subject == "platform"
    entries = cast("list[dict[str, object]]", rotated.jwks()["keys"])
    assert [item["kid"] for item in entries] == ["k1", "k2"]

    dropped = JwtServiceTokenIssuer(issuer="bms", keys=[new], active_kid="k2")
    with pytest.raises(AuthError):
        dropped.verify(old_token)


@pytest.mark.kiwi_id(2180)
async def test_signing_key_selection_errors() -> None:
    """签发密钥选择：无签名私钥 / active_kid 非法 / 多密钥未指定均拒。"""
    public_only = JwtServiceTokenIssuer(issuer="bms", keys=[TokenKey(kid="p", public_key=_rsa_key().public_key)])
    with pytest.raises(ConfigError):
        await public_only.issue(ServiceTokenSpec(service="platform"))

    wrong_kid = JwtServiceTokenIssuer(issuer="bms", keys=[_rsa_key("k1")], active_kid="missing")
    with pytest.raises(ConfigError):
        await wrong_kid.issue(ServiceTokenSpec(service="platform"))

    ambiguous = JwtServiceTokenIssuer(issuer="bms", keys=[_rsa_key("k1"), _rsa_key("k2")])
    with pytest.raises(ConfigError):
        await ambiguous.issue(ServiceTokenSpec(service="platform"))

    single = JwtServiceTokenIssuer(issuer="bms", keys=[_rsa_key("only")])
    assert (await single.issue(ServiceTokenSpec(service="platform"))).access_token


@pytest.mark.kiwi_id(2180)
def test_settings_and_factory() -> None:
    """配置解析（keys 字典）与工厂构造；无密钥构造不拒（校验方）。"""
    key = _rsa_key()
    settings = Settings(
        service_token=ServiceTokenSettings(
            provider="jwt",
            issuer="bms-test",
            ttl_seconds=120,
            active_kid="k1",
            keys={"k1": TokenKeySettings(algorithm="RS256", public_key=key.public_key, private_key=key.private_key)},
        )
    )
    issuer = JwtServiceTokenIssuerFactory(settings).create(None)
    assert isinstance(issuer, JwtServiceTokenIssuer)
    assert issuer.plugin_name == "jwt"
    token = asyncio.run(issuer.issue(ServiceTokenSpec(service="platform")))
    assert token.expires_in == 120
    assert issuer.verify(token.access_token).issuer == "bms-test"

    empty = JwtServiceTokenIssuerFactory(Settings(service_token=ServiceTokenSettings(provider="jwt"))).create(None)
    assert empty.jwks() == {"keys": []}
    with pytest.raises(ConfigError):
        asyncio.run(empty.issue(ServiceTokenSpec(service="platform")))


@pytest.mark.kiwi_id(2180)
def test_settings_env_injected_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """私钥经环境变量注入（kid 键位）可解析。"""
    key = _rsa_key()
    monkeypatch.setenv("BMS_SERVICE_TOKEN__KEYS__K1__PUBLIC_KEY", key.public_key)
    monkeypatch.setenv("BMS_SERVICE_TOKEN__KEYS__K1__PRIVATE_KEY", key.private_key)
    monkeypatch.setenv("BMS_SERVICE_TOKEN__ACTIVE_KID", "k1")
    settings = Settings()
    assert settings.service_token.keys["k1"].private_key.strip() == key.private_key.strip()
    issuer = JwtServiceTokenIssuerFactory(settings).create(None)
    assert asyncio.run(issuer.issue(ServiceTokenSpec(service="platform"))).access_token


@pytest.mark.kiwi_id(2180)
def test_null_service_token_issuer() -> None:
    """占位实现：固定占位令牌 / 空 JWKS / 占位声明。"""
    issuer = NullServiceTokenIssuer()
    token = asyncio.run(issuer.issue(ServiceTokenSpec(service="platform", scopes=("a",))))
    assert token.access_token == NULL_ACCESS_TOKEN
    assert issuer.jwks() == {"keys": []}
    assert issuer.verify("any").subject == "null-service"


@pytest.mark.kiwi_id(2180)
def test_realm_deployment_audience_mapper() -> None:
    """部署件护栏：realm 客户端含 `aud=api` audience mapper，且无明文密钥。"""
    realm = json.loads(_REALM_FILE.read_text(encoding="utf-8"))
    client = next(item for item in realm["clients"] if item["clientId"] == "bms-backend")
    assert client["secret"] == "${KEYCLOAK_CLIENT_SECRET}"
    mapper = next(item for item in client["protocolMappers"] if item["name"] == "aud-api")
    assert mapper["protocolMapper"] == "oidc-audience-mapper"
    assert mapper["config"]["included.custom.audience"] == "api"
    assert mapper["config"]["access.token.claim"] == "true"
