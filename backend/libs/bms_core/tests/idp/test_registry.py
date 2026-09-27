"""身份源行配置实例化测试（Kiwi 2197）：密钥引用解析、按 type 分派与缓存失效。"""

import pytest

from bms_core.core.exceptions import ConfigError
from bms_core.idp.oidc import OidcIdentityProvider
from bms_core.idp.registry import (
    IdentityProviderRegistry,
    IdentityProviderSpec,
    resolve_secret_ref,
)


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
