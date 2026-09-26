"""用户令牌自签 · 能力域测试（Kiwi 2193）：签发契约 / 类型强校验 / 轮换 / 前缀 / 失败分支 / Null / 工厂。

本机以 joserfc 生成密钥对，无需外部依赖；校验源切换的端到端断言见 `test_token_verifier.py`，
mjbk 真机冒烟见任务测试记录。
"""

import asyncio
import time
from typing import cast

import pytest
from joserfc import jwt
from joserfc.jwk import ECKey, RSAKey

from bms_core.core.capability import BaseNullObject
from bms_core.core.config import SecuritySettings, Settings, TokenKeySettings, UserTokenSettings
from bms_core.core.exceptions import AuthError, ConfigError, ParamError
from bms_core.oauth.keys import TokenKey, merge_jwks
from bms_core.oauth.null import NullUserTokenIssuer
from bms_core.oauth.token import TOKEN_AUDIENCE_API, TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.user_jwt import JwtUserTokenIssuer, JwtUserTokenIssuerFactory
from bms_core.oauth.user_token import (
    DEFAULT_USER_TOKEN_ISSUER,
    USER_TOKEN_KID_PREFIX,
    USER_TOKEN_TYPE_ACCESS,
    USER_TOKEN_TYPE_REFRESH,
    BaseUserTokenIssuer,
    UserTokenPair,
    UserTokenSpec,
)

_ACCESS_TTL = 1800
_REFRESH_TTL = 1209600


def _rsa_key(kid: str = "usr-k1") -> TokenKey:
    """生成 RSA 密钥 TokenKey（RS256）。

    Args:
        kid: 密钥标识（须带 `usr-` 前缀）。

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


def _ec_key(kid: str = "usr-e1") -> TokenKey:
    """生成 EC 密钥 TokenKey（ES256）。

    Args:
        kid: 密钥标识（须带 `usr-` 前缀）。

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


def _issuer(
    *,
    keys: list[TokenKey] | None = None,
    active_kid: str = "usr-k1",
    issuer: str = DEFAULT_USER_TOKEN_ISSUER,
    access_ttl: int = _ACCESS_TTL,
    refresh_ttl: int = _REFRESH_TTL,
) -> JwtUserTokenIssuer:
    """构造用户令牌签发者。

    Args:
        keys: 密钥集（缺省单把 `usr-k1`）。
        active_kid: 当前签名密钥 kid。
        issuer: 签发方。
        access_ttl: access 有效期（秒）。
        refresh_ttl: refresh 有效期（秒）。

    Returns:
        JwtUserTokenIssuer: 签发者。
    """
    return JwtUserTokenIssuer(
        issuer=issuer,
        keys=keys if keys is not None else [_rsa_key()],
        active_kid=active_kid,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
    )


def _craft(key: TokenKey, claims: dict[str, object], *, kid: str | None = None) -> str:
    """用给定密钥手工签发令牌（负向用例：伪造 aud / iss / 类型 / 缺声明）。

    Args:
        key: 签名密钥。
        claims: 声明。
        kid: JOSE header kid（缺省取密钥 kid）。

    Returns:
        str: 紧凑 JWT。
    """
    header = {"alg": key.algorithm, "kid": kid or key.kid}
    return jwt.encode(header, claims, key.signing_key())


def _claims(**overrides: object) -> dict[str, object]:
    """构造合法用户令牌声明（可覆盖字段）。

    Args:
        **overrides: 覆盖字段。

    Returns:
        dict[str, object]: 声明。
    """
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": DEFAULT_USER_TOKEN_ISSUER,
        "sub": "1001",
        "aud": TOKEN_AUDIENCE_API,
        "jti": "sess-1",
        "type": USER_TOKEN_TYPE_ACCESS,
        "exp": now + 300,
        "iat": now - 60,
    }
    claims.update(overrides)
    return claims


@pytest.mark.kiwi_id(2193)
def test_constants_and_contract() -> None:
    """常量与契约继承链（插件键 / kid 前缀 / 类型 / 默认签发方）。"""
    assert USER_TOKEN_KID_PREFIX == "usr-"
    assert USER_TOKEN_TYPE_ACCESS == "access"
    assert USER_TOKEN_TYPE_REFRESH == "refresh"
    assert DEFAULT_USER_TOKEN_ISSUER == "bms"
    assert BaseUserTokenIssuer.key == BaseUserTokenIssuer.plugin_key == "user_token"
    assert issubclass(JwtUserTokenIssuer, BaseUserTokenIssuer)
    assert issubclass(NullUserTokenIssuer, BaseUserTokenIssuer)
    assert issubclass(NullUserTokenIssuer, BaseNullObject)
    spec = UserTokenSpec(subject="1001", session_id="sess-1")
    assert spec.tenant_id is None and spec.scopes == ()


@pytest.mark.kiwi_id(2193)
async def test_issue_pair_claims_and_ttls() -> None:
    """签发双 token：access / refresh claims 与 TTL、`jti` 同值、可选 tenant / scope 回填。"""
    issuer = _issuer()
    pair = await issuer.issue_pair(
        UserTokenSpec(subject="1001", session_id="sess-1", tenant_id="acme", scopes=("user:read", "org:read"))
    )
    assert isinstance(pair, UserTokenPair)
    assert pair.token_type == "Bearer"
    assert pair.expires_in == _ACCESS_TTL
    assert pair.refresh_expires_in == _REFRESH_TTL
    assert pair.session_id == "sess-1"
    assert pair.scopes == ("user:read", "org:read")

    access = issuer.verify(pair.access_token, expected_type=USER_TOKEN_TYPE_ACCESS)
    refresh = issuer.verify(pair.refresh_token, expected_type=USER_TOKEN_TYPE_REFRESH)
    assert access.subject == "1001"
    assert access.issuer == DEFAULT_USER_TOKEN_ISSUER
    assert access.audience == (TOKEN_AUDIENCE_API,)
    payload = dict(access.payload)
    assert payload["type"] == USER_TOKEN_TYPE_ACCESS
    assert payload["tenant_id"] == "acme"
    assert payload["scope"] == "user:read org:read"
    assert payload["jti"] == "sess-1"
    assert access.expires_at - access.issued_at == _ACCESS_TTL
    assert refresh.payload["type"] == USER_TOKEN_TYPE_REFRESH
    assert refresh.payload["jti"] == "sess-1"
    assert refresh.expires_at - refresh.issued_at == _REFRESH_TTL

    minimal = await issuer.issue_pair(UserTokenSpec(subject="1002", session_id="sess-2"))
    minimal_payload = dict(issuer.verify(minimal.access_token, expected_type=USER_TOKEN_TYPE_ACCESS).payload)
    assert "tenant_id" not in minimal_payload
    assert "scope" not in minimal_payload


@pytest.mark.kiwi_id(2193)
async def test_issue_pair_ec_algorithm() -> None:
    """ES256 密钥可签发双 token 并通过本地验签。"""
    issuer = _issuer(keys=[_ec_key()], active_kid="usr-e1")
    pair = await issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))
    assert issuer.verify(pair.access_token, expected_type=USER_TOKEN_TYPE_ACCESS).subject == "1001"


@pytest.mark.kiwi_id(2193)
async def test_issue_pair_rejects_blank_fields() -> None:
    """主体 / 会话 id 为空即参数错误（不签发）。"""
    issuer = _issuer()
    with pytest.raises(ParamError):
        await issuer.issue_pair(UserTokenSpec(subject="  ", session_id="sess-1"))
    with pytest.raises(ParamError):
        await issuer.issue_pair(UserTokenSpec(subject="1001", session_id=" "))


@pytest.mark.kiwi_id(2193)
def test_kid_prefix_required() -> None:
    """用户令牌密钥 kid 必须带 `usr-` 前缀（构造即拒，拒绝装配）。"""
    with pytest.raises(ConfigError):
        _issuer(keys=[_rsa_key("k1")], active_kid="k1")


@pytest.mark.kiwi_id(2193)
async def test_type_strict_check() -> None:
    """类型强校验：refresh 不得当 access、access 不得当 refresh、类型缺失 / 非法均拒。"""
    key = _rsa_key()
    issuer = _issuer(keys=[key], active_kid="usr-k1")
    pair = await issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))
    with pytest.raises(AuthError):
        issuer.verify(pair.refresh_token, expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        issuer.verify(pair.access_token, expected_type=USER_TOKEN_TYPE_REFRESH)

    no_type = _craft(key, {k: v for k, v in _claims().items() if k != "type"})
    with pytest.raises(AuthError):
        issuer.verify(no_type, expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        issuer.verify(_craft(key, _claims(type="other")), expected_type=USER_TOKEN_TYPE_ACCESS)


@pytest.mark.kiwi_id(2193)
async def test_missing_subject_or_jti_rejected() -> None:
    """`sub` / `jti` 缺失即拒（会话标记与身份头都依赖这两个声明）。"""
    key = _rsa_key()
    issuer = _issuer(keys=[key], active_kid="usr-k1")
    with pytest.raises(AuthError):
        issuer.verify(_craft(key, _claims(sub="")), expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        issuer.verify(_craft(key, _claims(jti="")), expected_type=USER_TOKEN_TYPE_ACCESS)


@pytest.mark.kiwi_id(2193)
async def test_expired_wrong_aud_wrong_issuer_and_tampered_rejected() -> None:
    """过期 / `aud` / `iss` 不符 / 篡改签名均抛认证错误（伪造分支）。"""
    key = _rsa_key()
    issuer = _issuer(keys=[key], access_ttl=-3600)
    expired = (await issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))).access_token
    with pytest.raises(AuthError):
        issuer.verify(expired, expected_type=USER_TOKEN_TYPE_ACCESS)

    fresh = _issuer(keys=[key], access_ttl=_ACCESS_TTL)
    with pytest.raises(AuthError):
        fresh.verify(_craft(key, _claims(aud=TOKEN_AUDIENCE_SERVICE)), expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        fresh.verify(_craft(key, _claims(iss="other")), expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        fresh.verify(_craft(_rsa_key("usr-other"), _claims()), expected_type=USER_TOKEN_TYPE_ACCESS)
    with pytest.raises(AuthError):
        fresh.verify(_craft(key, _claims(), kid="usr-unknown"), expected_type=USER_TOKEN_TYPE_ACCESS)


@pytest.mark.kiwi_id(2193)
async def test_key_rotation_parallel_verification() -> None:
    """多密钥并行：新 kid 签发、旧 kid 票据在新密钥集下仍可验，淘汰后拒绝。"""
    old, new = _rsa_key("usr-old"), _rsa_key("usr-new")
    first = _issuer(keys=[old], active_kid="usr-old")
    old_token = (await first.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))).access_token

    rotated = _issuer(keys=[old, new], active_kid="usr-new")
    new_pair = await rotated.issue_pair(UserTokenSpec(subject="1002", session_id="sess-2"))
    assert rotated.verify(new_pair.access_token, expected_type=USER_TOKEN_TYPE_ACCESS).subject == "1002"
    assert rotated.verify(old_token, expected_type=USER_TOKEN_TYPE_ACCESS).subject == "1001"

    dropped = _issuer(keys=[new], active_kid="usr-new")
    with pytest.raises(AuthError):
        dropped.verify(old_token, expected_type=USER_TOKEN_TYPE_ACCESS)


@pytest.mark.kiwi_id(2193)
async def test_signing_key_selection_errors() -> None:
    """签发密钥选择：无签名私钥 / `active_kid` 未命中 / 多密钥未指定均拒；单私钥自动可选。"""
    public_only = _issuer(keys=[TokenKey(kid="usr-p", public_key=_rsa_key().public_key)], active_kid="")
    with pytest.raises(ConfigError):
        await public_only.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))

    wrong_kid = _issuer(active_kid="usr-missing")
    with pytest.raises(ConfigError):
        await wrong_kid.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))

    ambiguous = _issuer(keys=[_rsa_key("usr-k1"), _rsa_key("usr-k2")], active_kid="")
    with pytest.raises(ConfigError):
        await ambiguous.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))

    single = _issuer(keys=[_rsa_key("usr-only")], active_kid="")
    assert (await single.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))).access_token


@pytest.mark.kiwi_id(2193)
async def test_no_keys_fail_closed_on_use() -> None:
    """密钥集为空：允许构造（校验方只需公钥）、签发 `ConfigError`、验签 `AuthError`。"""
    issuer = _issuer(keys=[], active_kid="")
    assert issuer.jwks() == {"keys": []}
    with pytest.raises(ConfigError):
        await issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1"))
    with pytest.raises(AuthError):
        issuer.verify("any", expected_type=USER_TOKEN_TYPE_ACCESS)


@pytest.mark.kiwi_id(2193)
def test_jwks_public_only_and_merge_conflict() -> None:
    """`jwks` 只含公钥、按 kid 排序；`merge_jwks` 合并两类公钥、kid 冲突 / 结构非法即拒。"""
    issuer = _issuer(keys=[_rsa_key("usr-k2"), _rsa_key("usr-k1")], active_kid="usr-k1")
    entries = cast("list[dict[str, object]]", issuer.jwks()["keys"])
    assert [item["kid"] for item in entries] == ["usr-k1", "usr-k2"]
    assert all("d" not in item for item in entries)

    merged = merge_jwks(issuer.jwks(), {"keys": [{"kid": "svc-k1", "kty": "RSA"}]})
    merged_entries = cast("list[dict[str, object]]", merged["keys"])
    assert [item["kid"] for item in merged_entries] == ["svc-k1", "usr-k1", "usr-k2"]

    with pytest.raises(ConfigError):
        merge_jwks(issuer.jwks(), {"keys": [{"kid": "usr-k1", "kty": "RSA"}]})
    with pytest.raises(ConfigError):
        merge_jwks({"nokeys": []})
    with pytest.raises(ConfigError):
        merge_jwks({"keys": [{"kty": "RSA"}]})
    with pytest.raises(ConfigError):
        merge_jwks({"keys": ["bad"]})


@pytest.mark.kiwi_id(2193)
def test_null_issuer_fail_closed() -> None:
    """Null 实现：签发 `ConfigError`、验签 `AuthError`、空 JWKS（fail-closed）。"""
    issuer = NullUserTokenIssuer()
    with pytest.raises(ConfigError):
        asyncio.run(issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1")))
    with pytest.raises(AuthError):
        issuer.verify("any", expected_type=USER_TOKEN_TYPE_ACCESS)
    assert issuer.jwks() == {"keys": []}


@pytest.mark.kiwi_id(2193)
def test_settings_and_factory() -> None:
    """工厂：读 `[user_token].issuer` 与 `[security]` 密钥 / TTL；空密钥构造不拒、签发才拒。"""
    key = _rsa_key()
    settings = Settings(
        user_token=UserTokenSettings(provider="jwt", issuer="bms-test"),
        security=SecuritySettings(
            access_token_expire_minutes=30,
            refresh_token_expire_days=14,
            active_kid="usr-k1",
            keys={
                "usr-k1": TokenKeySettings(algorithm="RS256", public_key=key.public_key, private_key=key.private_key)
            },
        ),
    )
    issuer = JwtUserTokenIssuerFactory(settings).create(None)
    assert isinstance(issuer, JwtUserTokenIssuer)
    assert issuer.plugin_name == "jwt"
    pair = asyncio.run(issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1")))
    assert pair.expires_in == 30 * 60
    assert pair.refresh_expires_in == 14 * 86400
    assert issuer.verify(pair.access_token, expected_type=USER_TOKEN_TYPE_ACCESS).issuer == "bms-test"

    default_issuer = JwtUserTokenIssuerFactory(
        Settings(user_token=UserTokenSettings(provider="jwt"), security=SecuritySettings())
    ).create(None)
    assert default_issuer.jwks() == {"keys": []}

    bad_prefix = Settings(
        user_token=UserTokenSettings(provider="jwt"),
        security=SecuritySettings(
            active_kid="k1",
            keys={"k1": TokenKeySettings(algorithm="RS256", public_key=key.public_key, private_key=key.private_key)},
        ),
    )
    with pytest.raises(ConfigError):
        JwtUserTokenIssuerFactory(bad_prefix).create(None)


@pytest.mark.kiwi_id(2193)
def test_settings_env_injected_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """私钥经环境变量按键位注入（`usr-` 前缀 kid）可解析。"""
    key = _rsa_key()
    monkeypatch.setenv("BMS_SECURITY__KEYS__USR-K1__PUBLIC_KEY", key.public_key)
    monkeypatch.setenv("BMS_SECURITY__KEYS__USR-K1__PRIVATE_KEY", key.private_key)
    monkeypatch.setenv("BMS_SECURITY__ACTIVE_KID", "usr-k1")
    settings = Settings()
    assert settings.security.keys["usr-k1"].private_key.strip() == key.private_key.strip()
    issuer = JwtUserTokenIssuerFactory(settings).create(None)
    pair = asyncio.run(issuer.issue_pair(UserTokenSpec(subject="1001", session_id="sess-1")))
    assert issuer.verify(pair.access_token, expected_type=USER_TOKEN_TYPE_ACCESS).subject == "1001"
