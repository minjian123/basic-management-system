"""身份源行配置声明式校验与凭据脱敏测试（Kiwi 2203）。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import IdpConfigInvalidError
from bms_core.idp.schema import has_secret, mask_provider_config, validate_provider_config

_OIDC = {
    "issuer": "https://idp.example.com/realms/bms",
    "client_id": "bms-backend",
    "client_secret_ref": "env:IDP_SECRET",
    "redirect_uri": "https://app.example.com/api/v1/auth/sso/keycloak/callback",
}


def _validate(
    protocol: str, config: ConcurrentStableDict[str, object], *, allow_private: bool = False
) -> ConcurrentStableDict[str, object]:
    """调用校验（默认不允许私网）。"""
    return ConcurrentStableDict(validate_provider_config(protocol, config, allow_private_hosts=allow_private))


@pytest.mark.kiwi_id(2203)
def test_valid_configs_and_normalization() -> None:
    """四协议合法配置通过并归一化（去空白 / 去重）。"""
    assert _validate("oidc", ConcurrentStableDict(dict(_OIDC)))["client_id"] == "bms-backend"
    assert _validate("oidc", ConcurrentStableDict({**_OIDC, "discovery_cache_ttl": 120}))["discovery_cache_ttl"] == 120
    cas = _validate(
        "cas",
        ConcurrentStableDict({"cas_server_url": "https://cas.example.com/cas", "attribute_map": {"email": ["mail"]}}),
    )
    assert cas["attribute_map"] == {"email": ["mail"]}
    wecom = _validate(
        "wecom",
        ConcurrentStableDict(
            {"corp_id": "corp-1", "agent_id": "agent-1", "secret_ref": "env:WECOM_SECRET", "mode": "oauth"}
        ),
    )
    assert wecom["mode"] == "oauth"
    dingtalk = _validate("dingtalk", ConcurrentStableDict({"client_id": "c-1", "client_secret_ref": "env:DT_SECRET"}))
    assert dingtalk["client_id"] == "c-1"


@pytest.mark.kiwi_id(2203)
def test_shared_keys_types() -> None:
    """通用键 `jit_enabled`（bool）与 `allowed_email_domains`（字符串数组）类型校验。"""
    config: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            **_OIDC,
            "jit_enabled": True,
            "allowed_email_domains": ["example.com", "example.com", "corp.cn"],
        }
    )
    normalized = _validate("oidc", config)
    assert normalized["jit_enabled"] is True
    assert normalized["allowed_email_domains"] == ["example.com", "corp.cn"]

    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "jit_enabled": "yes"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "allowed_email_domains": "example.com"}))


@pytest.mark.kiwi_id(2203)
def test_unknown_key_and_protocol_rejected() -> None:
    """未知键与不支持的协议类型拒绝（20064）。"""
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "bogus": 1}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("saml", ConcurrentStableDict(dict(_OIDC)))


@pytest.mark.kiwi_id(2203)
def test_required_and_type_errors() -> None:
    """必填缺失 / 类型非法 / 枚举非法拒绝。"""
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({"issuer": "https://idp.example.com", "client_id": "c"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "scopes": "openid"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate(
            "wecom",
            ConcurrentStableDict({"corp_id": "c", "agent_id": "a", "secret_ref": "env:S", "mode": "bogus"}),
        )
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "discovery_cache_ttl": "soon"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "client_id": "   "}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "scopes": ["openid", 7]}))
    with pytest.raises(IdpConfigInvalidError):
        _validate(
            "cas",
            ConcurrentStableDict({"cas_server_url": "https://cas.example.com/cas", "attribute_map": ["x"]}),
        )
    with pytest.raises(IdpConfigInvalidError):
        _validate(
            "cas",
            ConcurrentStableDict({"cas_server_url": "https://cas.example.com/cas", "attribute_map": {"email": "mail"}}),
        )


@pytest.mark.kiwi_id(2203)
def test_outbound_url_ssrf_rejected() -> None:
    """出站键（issuer / api_base_url）经 SSRF 校验拒绝内网，放行公网。"""
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "issuer": "http://10.0.0.5"}))
    assert (
        _validate("oidc", ConcurrentStableDict({**_OIDC, "issuer": "https://idp.example.com"}))["issuer"]
        == "https://idp.example.com"
    )
    private_ok = validate_provider_config(
        "oidc",
        ConcurrentStableDict({**_OIDC, "issuer": "http://127.0.0.1:8090"}),
        allow_private_hosts=True,
    )
    assert private_ok["issuer"] == "http://127.0.0.1:8090"


@pytest.mark.kiwi_id(2203)
def test_secret_ref_only_env() -> None:
    """密钥引用只接受 `env:变量名`；`secret:` 与疑似明文拒绝。"""
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "client_secret_ref": "secret:abc"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "client_secret_ref": "plain-secret-value"}))
    with pytest.raises(IdpConfigInvalidError):
        _validate("oidc", ConcurrentStableDict({**_OIDC, "client_secret_ref": "   "}))


@pytest.mark.kiwi_id(2203)
def test_mask_and_has_secret() -> None:
    """脱敏：敏感键掩码为 `env:***`，非敏感键原样；`has_secret` 反映是否已配置。"""
    config = {**_OIDC, "client_secret_ref": "env:IDP_SECRET"}
    masked = mask_provider_config("oidc", ConcurrentStableDict(config))
    assert masked["client_secret_ref"] == "env:***"
    assert masked["client_id"] == "bms-backend"
    assert has_secret("oidc", ConcurrentStableDict(config)) is True
    assert has_secret("oidc", ConcurrentStableDict({**_OIDC, "client_secret_ref": ""})) is False
    assert (
        mask_provider_config("oidc", ConcurrentStableDict({"client_secret_ref": "weird"}))["client_secret_ref"] == "***"
    )
    assert mask_provider_config("unknown", ConcurrentStableDict({"client_secret": "plain"})) == {}
    dirty = mask_provider_config("oidc", ConcurrentStableDict({**_OIDC, "legacy_secret_ref": "env:X"}))
    assert dirty["legacy_secret_ref"] == "env:***"
