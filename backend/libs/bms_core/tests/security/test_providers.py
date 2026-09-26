"""security 能力域 · 提供者装配测试（Kiwi 2192）：真实实现解析 / 回落 null / 契约版本。"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

from bms_core.core import plugin as plugin_module
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import PluginError
from bms_core.core.plugin import PluginRegistry
from bms_core.security.base import (
    get_password_hasher,
    get_session_security,
    get_token_codec,
)
from bms_core.security.jwt import JwtTokenCodec
from bms_core.security.null import NullPasswordHasher, NullSessionSecurity, NullTokenCodec
from bms_core.security.pbkdf2 import PBKDF2_MIN_ITERATIONS, Pbkdf2PasswordHasher
from bms_core.security.session import DefaultSessionSecurity


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身（仅 `app.state.settings` 被读取）。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))


def _registry(monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    """构造隔离注册表（登记真实与 Null 实现）。

    Args:
        monkeypatch: pytest 补丁夹具。

    Returns:
        PluginRegistry: 隔离注册表。
    """
    registry = PluginRegistry()
    registry.register("password_hasher", "pbkdf2", lambda: Pbkdf2PasswordHasher(iterations=PBKDF2_MIN_ITERATIONS))
    registry.register("password_hasher", "null", lambda: NullPasswordHasher())
    registry.register("token_codec", "jwt", lambda: JwtTokenCodec(keys=()))
    registry.register("token_codec", "null", lambda: NullTokenCodec())
    registry.register("session_security", "default", lambda: DefaultSessionSecurity(secret_key=""))
    registry.register("session_security", "null", lambda: NullSessionSecurity())
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)
    return registry


@pytest.mark.kiwi_id(2192)
def test_resolves_real_implementations(monkeypatch: pytest.MonkeyPatch) -> None:
    """按配置解析到真实实现（应用级单例，同 provider 复用实例）。"""
    _registry(monkeypatch)
    settings = Settings(
        password_hasher=PluginSelection(provider="pbkdf2"),
        token_codec=PluginSelection(provider="jwt"),
        session_security=PluginSelection(provider="default"),
    )
    request = _request(settings)
    assert isinstance(get_password_hasher(request), Pbkdf2PasswordHasher)
    assert isinstance(get_token_codec(request), JwtTokenCodec)
    assert isinstance(get_session_security(request), DefaultSessionSecurity)
    assert get_password_hasher(request) is get_password_hasher(request)


@pytest.mark.kiwi_id(2192)
def test_falls_back_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 为空回落 Null 实现（fail-closed 由实现保证）。"""
    _registry(monkeypatch)
    request = _request(
        Settings(
            password_hasher=PluginSelection(provider=""),
            token_codec=PluginSelection(provider=""),
            session_security=PluginSelection(provider=""),
        )
    )
    assert isinstance(get_password_hasher(request), NullPasswordHasher)
    assert isinstance(get_token_codec(request), NullTokenCodec)
    assert isinstance(get_session_security(request), NullSessionSecurity)


@pytest.mark.kiwi_id(2192)
def test_contract_version_mismatch_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """契约版本主版本不匹配即拒（PluginError）。"""
    registry = _registry(monkeypatch)

    class FutureHasher:
        """构造期声明未来主版本的实现替身。"""

        contract_version = "9.0.0"

    registry.register("password_hasher", "future", lambda: FutureHasher())
    request = _request(Settings(password_hasher=PluginSelection(provider="future")))
    with pytest.raises(PluginError):
        get_password_hasher(request)
