"""身份源行配置实例化测试（Kiwi 2197）：密钥引用解析、按 type 分派与缓存失效。"""

import pytest

from bms_core.core.exceptions import ConfigError, DingtalkConfigError, WecomConfigError
from bms_core.idp.cas import CasIdentityProvider
from bms_core.idp.dingtalk import DingtalkIdentityProvider
from bms_core.idp.oidc import OidcIdentityProvider
from bms_core.idp.registry import (
    IdentityProviderRegistry,
    IdentityProviderSpec,
    resolve_secret_ref,
)
from bms_core.idp.wecom import WecomIdentityProvider


@pytest.mark.kiwi_id(2197)
def test_resolve_secret_ref_env_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """`env:` 引用解析明文；空引用 / 变量缺失 / `secret:` / 未知前缀均抛配置错误。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    assert resolve_secret_ref("env:IDP_TEST_SECRET") == "s3cr3t"

    with pytest.raises(ConfigError):
        resolve_secret_ref("")
    with pytest.raises(ConfigError):
        resolve_secret_ref("env:IDP_TEST_MISSING")
    with pytest.raises(ConfigError):
        resolve_secret_ref("secret:abc")
    with pytest.raises(ConfigError):
        resolve_secret_ref("vault:abc")


def _spec(
    *,
    config: dict[str, object] | None = None,
    idp_key: str = "demo:keycloak",
    updated_at: str = "2026-09-27T00:00:00+00:00",
) -> IdentityProviderSpec:
    """构造行配置视图（默认 OIDC 必填齐备）。"""
    merged: dict[str, object] = {
        "issuer": "http://idp.test/realms/bms",
        "client_id": "bms-backend",
        "client_secret_ref": "env:IDP_TEST_SECRET",
        "redirect_uri": "http://app.test/api/v1/auth/sso/keycloak/callback",
    }
    if config is not None:
        merged.update(config)
    return IdentityProviderSpec(id=1, idp_key=idp_key, type="oidc", config=merged, updated_at=updated_at)


@pytest.mark.kiwi_id(2197)
def test_build_oidc_from_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """按行配置构造 OIDC 实例（密钥引用转明文；scopes / 缓存 TTL 可选注入）。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    instance = registry.build(_spec(config={"scopes": ["openid", "profile"], "discovery_cache_ttl": 60}))
    assert isinstance(instance, OidcIdentityProvider)
    assert instance._issuer == "http://idp.test/realms/bms"  # pyright: ignore[reportPrivateUsage]
    assert instance._client_id == "bms-backend"  # pyright: ignore[reportPrivateUsage]
    assert instance._client_secret == "s3cr3t"  # pyright: ignore[reportPrivateUsage]
    assert instance._redirect_uri == "http://app.test/api/v1/auth/sso/keycloak/callback"  # pyright: ignore[reportPrivateUsage]
    assert instance._scopes == ("openid", "profile")  # pyright: ignore[reportPrivateUsage]
    assert instance._discovery_cache_ttl == 60.0  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2197)
def test_build_rejects_missing_config_and_unknown_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """必填缺失（issuer / 密钥引用）与未支持协议类型均抛配置错误。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    with pytest.raises(ConfigError):
        registry.build(_spec(config={"issuer": ""}))
    with pytest.raises(ConfigError):
        registry.build(_spec(config={"client_secret_ref": ""}))
    with pytest.raises(ConfigError):
        registry.build(_spec(config={"client_secret_ref": "env:IDP_TEST_MISSING"}))
    with pytest.raises(ConfigError):
        registry.build(IdentityProviderSpec(id=2, idp_key="demo:saml", type="saml", config={}, updated_at="t"))


@pytest.mark.kiwi_id(2197)
def test_get_caches_until_row_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    """实例缓存键 `(id, updated_at, type)`：同键命中；行更新后失效重建；clear 清空。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    spec = _spec()
    first = registry.get(spec)
    assert registry.get(spec) is first

    updated = _spec(updated_at="2026-09-27T01:00:00+00:00")
    second = registry.get(updated)
    assert second is not first

    registry.clear()
    third = registry.get(updated)
    assert third is not second


@pytest.mark.kiwi_id(2197)
def test_custom_secret_resolver_injected() -> None:
    """密钥解析器可注入（测试 / 未来 Secret 后端）；解析结果传入实例。"""
    registry = IdentityProviderRegistry(secret_resolver=lambda ref: f"resolved:{ref}")
    instance = registry.build(_spec())
    assert isinstance(instance, OidcIdentityProvider)
    assert instance._client_secret == "resolved:env:IDP_TEST_SECRET"  # pyright: ignore[reportPrivateUsage]


def _cas_spec(config: dict[str, object] | None = None) -> IdentityProviderSpec:
    """构造 CAS 行配置视图（默认必填齐备）。

    Args:
        config: 覆盖字段。

    Returns:
        IdentityProviderSpec: 行配置视图。
    """
    merged: dict[str, object] = {
        "cas_server_url": "https://cas.test/cas",
        "redirect_uri": "http://app.test/api/v1/auth/sso/cas/callback",
    }
    if config is not None:
        merged.update(config)
    return IdentityProviderSpec(id=3, idp_key="demo:cas", type="cas", config=merged, updated_at="t")


@pytest.mark.kiwi_id(2199)
def test_build_cas_from_spec() -> None:
    """按行配置构造 CAS 实例（路径可配、attribute_map 覆盖；CAS 不要求密钥）。"""
    registry = IdentityProviderRegistry()
    instance = registry.build(
        _cas_spec(
            {
                "cas_login_path": "/cas/login",
                "cas_service_validate_path": "/serviceValidate",
                "attribute_map": {"name": ["displayName"]},
            }
        )
    )
    assert isinstance(instance, CasIdentityProvider)
    assert instance._server_url == "https://cas.test/cas"  # pyright: ignore[reportPrivateUsage]
    assert instance._login_path == "/cas/login"  # pyright: ignore[reportPrivateUsage]
    assert instance._service_validate_path == "/serviceValidate"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2199)
def test_build_cas_rejects_missing_and_invalid_config() -> None:
    """CAS 必填缺失（cas_server_url / redirect_uri）与 attribute_map 非法类型均抛配置错误。"""
    registry = IdentityProviderRegistry()
    with pytest.raises(ConfigError):
        registry.build(_cas_spec({"cas_server_url": ""}))
    with pytest.raises(ConfigError):
        registry.build(_cas_spec({"redirect_uri": ""}))
    with pytest.raises(ConfigError):
        registry.build(_cas_spec({"attribute_map": ["uid"]}))


def _wecom_spec(config: dict[str, object] | None = None) -> IdentityProviderSpec:
    """构造企业微信行配置视图（默认必填齐备）。

    Args:
        config: 覆盖字段。

    Returns:
        IdentityProviderSpec: 行配置视图。
    """
    merged: dict[str, object] = {
        "corp_id": "corp-1",
        "agent_id": "agent-1",
        "secret_ref": "env:IDP_TEST_SECRET",
        "redirect_uri": "http://app.test/api/v1/auth/sso/wecom/callback",
    }
    if config is not None:
        merged.update(config)
    return IdentityProviderSpec(id=4, idp_key="demo:wecom", type="wecom", config=merged, updated_at="t")


@pytest.mark.kiwi_id(2200)
def test_build_wecom_from_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """按行配置构造企业微信实例（密钥引用转明文、mode / login_type 生效）。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    instance = registry.build(_wecom_spec({"mode": "oauth", "login_type": "ServiceApp"}))
    assert isinstance(instance, WecomIdentityProvider)
    assert instance._corp_id == "corp-1"  # pyright: ignore[reportPrivateUsage]
    assert instance._agent_id == "agent-1"  # pyright: ignore[reportPrivateUsage]
    assert instance._secret == "s3cr3t"  # pyright: ignore[reportPrivateUsage]
    assert instance._mode == "oauth"  # pyright: ignore[reportPrivateUsage]
    assert instance._login_type == "ServiceApp"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2200)
def test_build_wecom_rejects_missing_and_invalid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """企业微信必填缺失 / 密钥引用解析失败 / mode 非法均抛专用配置错误。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    with pytest.raises(WecomConfigError):
        registry.build(_wecom_spec({"corp_id": ""}))
    with pytest.raises(WecomConfigError):
        registry.build(_wecom_spec({"agent_id": ""}))
    with pytest.raises(WecomConfigError):
        registry.build(_wecom_spec({"secret_ref": "env:IDP_TEST_MISSING"}))
    with pytest.raises(WecomConfigError):
        registry.build(_wecom_spec({"mode": "bad"}))


def _dingtalk_spec(config: dict[str, object] | None = None) -> IdentityProviderSpec:
    """构造钉钉行配置视图（默认必填齐备）。

    Args:
        config: 覆盖字段。

    Returns:
        IdentityProviderSpec: 行配置视图。
    """
    merged: dict[str, object] = {
        "client_id": "client-1",
        "client_secret_ref": "env:IDP_TEST_SECRET",
        "redirect_uri": "http://app.test/api/v1/auth/sso/dingtalk/callback",
    }
    if config is not None:
        merged.update(config)
    return IdentityProviderSpec(id=5, idp_key="demo:dingtalk", type="dingtalk", config=merged, updated_at="t")


@pytest.mark.kiwi_id(2201)
def test_build_dingtalk_from_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """按行配置构造钉钉实例（密钥引用转明文、scope 生效）。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    instance = registry.build(_dingtalk_spec({"scope": "openid corpid"}))
    assert isinstance(instance, DingtalkIdentityProvider)
    assert instance._client_id == "client-1"  # pyright: ignore[reportPrivateUsage]
    assert instance._client_secret == "s3cr3t"  # pyright: ignore[reportPrivateUsage]
    assert instance._scope == "openid corpid"  # pyright: ignore[reportPrivateUsage]


@pytest.mark.kiwi_id(2201)
def test_build_dingtalk_rejects_missing_and_invalid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """钉钉必填缺失 / 密钥引用解析失败均抛专用配置错误。"""
    monkeypatch.setenv("IDP_TEST_SECRET", "s3cr3t")
    registry = IdentityProviderRegistry()
    with pytest.raises(DingtalkConfigError):
        registry.build(_dingtalk_spec({"client_id": ""}))
    with pytest.raises(DingtalkConfigError):
        registry.build(_dingtalk_spec({"client_secret_ref": "env:IDP_TEST_MISSING"}))
