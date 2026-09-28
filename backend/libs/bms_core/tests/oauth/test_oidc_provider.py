"""OIDC Provider 能力域测试（Kiwi 2202）：Discovery 文档、ID Token / access token 签发与校验、Null 实现。"""

import time
from typing import cast

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from bms_core.core.exceptions import AuthError, ConfigError, ParamError
from bms_core.idp.jwks import verify_jwt
from bms_core.oauth.keys import TokenKey, to_key_set
from bms_core.oauth.null import NullOidcProvider
from bms_core.oauth.oidc_jwt import JwtOidcProvider
from bms_core.oauth.oidc_provider import (
    OIDC_ACCESS_AUDIENCE,
    OIDC_TOKEN_TYPE_ACCESS,
    OIDC_TOKEN_TYPE_ID,
    AccessTokenSpec,
    IdTokenSpec,
    build_discovery_document,
)

ISS = "http://localhost:8000/api/v1/oidc"
CLIENT = "bms-demo-client"


def _keys() -> tuple[TokenKey, list[TokenKey]]:
    """生成一把测试密钥（kid=usr-k1）。

    Returns:
        tuple[TokenKey, list[TokenKey]]: (主密钥, 密钥集)。
    """
    key = RSAKey.generate_key(2048, private=True)
    token_key = TokenKey(
        kid="usr-k1",
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )
    return token_key, [token_key]


@pytest.mark.kiwi_id(2202)
def test_build_discovery_document_fields() -> None:
    """Discovery 文档：issuer / 四端点 / 关键 supported 字段齐全。"""
    doc = build_discovery_document(
        issuer=ISS,
        authorization_endpoint=f"{ISS}/authorize",
        token_endpoint=f"{ISS}/token",
        userinfo_endpoint=f"{ISS}/userinfo",
        jwks_uri=f"{ISS}/jwks",
    )
    assert doc["issuer"] == ISS
    assert doc["authorization_endpoint"] == f"{ISS}/authorize"
    assert doc["token_endpoint"] == f"{ISS}/token"
    assert doc["userinfo_endpoint"] == f"{ISS}/userinfo"
    assert doc["jwks_uri"] == f"{ISS}/jwks"
    assert doc["response_types_supported"] == ["code"]
    assert doc["grant_types_supported"] == ["authorization_code"]
    assert "S256" in cast("list[str]", doc["code_challenge_methods_supported"])
    assert "client_secret_basic" in cast("list[str]", doc["token_endpoint_auth_methods_supported"])
    assert doc["id_token_signing_alg_values_supported"] == ["RS256", "ES256"]


@pytest.mark.kiwi_id(2202)
async def test_id_token_roundtrip_and_claims() -> None:
    """ID Token：签发后本地验签，claims 含 iss / aud=client_id / typ=id_token / nonce / auth_time。"""
    _, keys = _keys()
    provider = JwtOidcProvider(keys=keys, active_kid="usr-k1", id_token_ttl=120)
    token = await provider.issue_id_token(
        IdTokenSpec(
            subject="1001",
            client_id=CLIENT,
            issuer=ISS,
            nonce="n-1",
            auth_time=1700000000,
            preferred_username="alice",
            name="Alice",
        )
    )
    claims = verify_jwt(token, to_key_set(keys), issuer=ISS, audience=CLIENT)
    assert claims.subject == "1001"
    assert claims.payload["typ"] == OIDC_TOKEN_TYPE_ID
    assert claims.payload["nonce"] == "n-1"
    assert claims.payload["auth_time"] == 1700000000
    assert claims.payload["preferred_username"] == "alice"
    assert claims.payload["name"] == "Alice"
    # 有效期取覆盖值
    assert claims.expires_at - claims.issued_at == 120


@pytest.mark.kiwi_id(2202)
@pytest.mark.kiwi_id(2217)
async def test_access_token_roundtrip_and_verify() -> None:
    """access token：签发 → verify_access_token 往返，claims 与 typ / aud 正确。"""
    _, keys = _keys()
    provider = JwtOidcProvider(keys=keys, active_kid="usr-k1", access_ttl=300)
    token = await provider.issue_access_token(
        AccessTokenSpec(subject="1001", tenant_id="1001", client_id=CLIENT, issuer=ISS, scopes=("openid", "profile"))
    )
    claims = provider.verify_access_token(token, issuer=ISS)
    assert claims.subject == "1001"
    assert claims.tenant_id == "1001"
    assert claims.client_id == CLIENT
    assert claims.scopes == ("openid", "profile")
    assert claims.token_id
    payload = jwt.decode(token, to_key_set(keys)).claims
    assert payload["aud"] == OIDC_ACCESS_AUDIENCE
    assert payload["typ"] == OIDC_TOKEN_TYPE_ACCESS


@pytest.mark.kiwi_id(2202)
async def test_access_token_rejects_wrong_issuer_and_type() -> None:
    """access token：issuer 不符拒；typ 非 idp_access 拒。"""
    token_key, keys = _keys()
    provider = JwtOidcProvider(keys=keys, active_kid="usr-k1")
    token = await provider.issue_access_token(AccessTokenSpec(subject="1", tenant_id="1001", issuer=ISS))
    with pytest.raises(AuthError):
        provider.verify_access_token(token, issuer="http://other/oidc")

    now = int(time.time())
    forged = jwt.encode(
        {"alg": "RS256", "kid": token_key.kid},
        {"iss": ISS, "sub": "1", "aud": OIDC_ACCESS_AUDIENCE, "typ": "access", "iat": now, "exp": now + 60},
        token_key.signing_key(),
    )
    with pytest.raises(AuthError):
        provider.verify_access_token(forged, issuer=ISS)


@pytest.mark.kiwi_id(2202)
async def test_issue_requires_signing_key() -> None:
    """无签名私钥时签发抛 ConfigError（fail-closed）。"""
    key = RSAKey.generate_key(2048, private=True)
    public_only = TokenKey(kid="usr-k1", algorithm="RS256", public_key=key.as_pem(private=False).decode())
    provider = JwtOidcProvider(keys=[public_only], active_kid="usr-k1")
    with pytest.raises(ConfigError):
        await provider.issue_id_token(IdTokenSpec(subject="1", client_id=CLIENT, issuer=ISS))


@pytest.mark.kiwi_id(2202)
def test_kid_prefix_enforced() -> None:
    """密钥 kid 缺 `usr-` 前缀即构造失败（ConfigError）。"""
    key = RSAKey.generate_key(2048, private=True)
    bad = TokenKey(
        kid="k1",
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )
    with pytest.raises(ConfigError):
        JwtOidcProvider(keys=[bad])


@pytest.mark.kiwi_id(2202)
async def test_param_and_empty_subject_errors() -> None:
    """签发缺主体抛 ParamError；空 sub 的 access token 校验抛 AuthError。"""
    token_key, keys = _keys()
    provider = JwtOidcProvider(keys=keys, active_kid="usr-k1")
    with pytest.raises(ParamError):
        await provider.issue_id_token(IdTokenSpec(subject="", client_id=CLIENT, issuer=ISS))
    with pytest.raises(ParamError):
        await provider.issue_access_token(AccessTokenSpec(subject="", issuer=ISS))

    now = int(time.time())
    forged = jwt.encode(
        {"alg": "RS256", "kid": token_key.kid},
        {
            "iss": ISS,
            "sub": "",
            "aud": OIDC_ACCESS_AUDIENCE,
            "typ": OIDC_TOKEN_TYPE_ACCESS,
            "iat": now,
            "exp": now + 60,
        },
        token_key.signing_key(),
    )
    with pytest.raises(AuthError):
        provider.verify_access_token(forged, issuer=ISS)


@pytest.mark.kiwi_id(2202)
async def test_single_signing_key_auto_selected() -> None:
    """单把签名私钥且未配 active_kid 时自动选用。"""
    _, keys = _keys()
    provider = JwtOidcProvider(keys=keys)
    token = await provider.issue_id_token(IdTokenSpec(subject="1", client_id=CLIENT, issuer=ISS))
    assert token


@pytest.mark.kiwi_id(2202)
async def test_signing_key_resolution_errors() -> None:
    """签名密钥解析：无签名密钥 / active_kid 未命中 / 多密钥未指定均 ConfigError。"""
    key = RSAKey.generate_key(2048, private=True)
    pub_only = TokenKey(kid="usr-k1", algorithm="RS256", public_key=key.as_pem(private=False).decode())
    with pytest.raises(ConfigError):
        await JwtOidcProvider(keys=[pub_only]).issue_id_token(IdTokenSpec(subject="1", client_id=CLIENT, issuer=ISS))

    signing = TokenKey(
        kid="usr-k1",
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )
    with pytest.raises(ConfigError):
        await JwtOidcProvider(keys=[signing], active_kid="usr-nope").issue_id_token(
            IdTokenSpec(subject="1", client_id=CLIENT, issuer=ISS)
        )

    other = RSAKey.generate_key(2048, private=True)
    signing2 = TokenKey(
        kid="usr-k2",
        algorithm="RS256",
        public_key=other.as_pem(private=False).decode(),
        private_key=other.as_pem(private=True).decode(),
    )
    with pytest.raises(ConfigError):
        await JwtOidcProvider(keys=[signing, signing2]).issue_access_token(AccessTokenSpec(subject="1", issuer=ISS))


@pytest.mark.kiwi_id(2202)
async def test_null_provider_fail_closed() -> None:
    """Null 实现：签发抛 ConfigError、校验抛 AuthError、jwks 空。"""
    provider = NullOidcProvider()
    assert provider.jwks() == {"keys": []}
    with pytest.raises(ConfigError):
        await provider.issue_id_token(IdTokenSpec(subject="1", client_id=CLIENT, issuer=ISS))
    with pytest.raises(ConfigError):
        await provider.issue_access_token(AccessTokenSpec(subject="1"))
    with pytest.raises(AuthError):
        provider.verify_access_token("whatever", issuer=ISS)
