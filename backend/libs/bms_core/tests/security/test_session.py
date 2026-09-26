"""security 能力域 · 会话安全测试（Kiwi 2192）：雪花会话 id / HMAC 指纹 / 黑名单键。"""

import pytest

from bms_core.core.config import SecuritySettings, Settings
from bms_core.security.session import (
    BLACKLIST_KEY_PREFIX,
    DefaultSessionSecurity,
    DefaultSessionSecurityFactory,
)


@pytest.mark.kiwi_id(2192)
def test_new_session_id() -> None:
    """会话 id 为雪花（十进制正整数字符串）且唯一。"""
    session = DefaultSessionSecurity(secret_key="s")
    first = session.new_session_id()
    second = session.new_session_id()
    assert first.isdigit()
    assert int(first) > 0
    assert first != second


@pytest.mark.kiwi_id(2192)
def test_fingerprint() -> None:
    """指纹确定性、随 ip / ua 变化、不落原始值（64 位十六进制）。"""
    session = DefaultSessionSecurity(secret_key="s")
    fingerprint = session.fingerprint(ip="10.0.0.1", user_agent="UA/1")
    assert fingerprint == session.fingerprint(ip="10.0.0.1", user_agent="UA/1")
    assert len(fingerprint) == 64
    assert "10.0.0.1" not in fingerprint
    assert "UA/1" not in fingerprint
    assert session.fingerprint(ip="10.0.0.2", user_agent="UA/1") != fingerprint
    assert session.fingerprint(ip="10.0.0.1", user_agent="UA/2") != fingerprint
    assert DefaultSessionSecurity(secret_key="other").fingerprint(ip="10.0.0.1", user_agent="UA/1") != fingerprint
    empty = session.fingerprint(ip=None, user_agent=None)
    assert len(empty) == 64
    assert empty == DefaultSessionSecurity(secret_key="s").fingerprint(ip=None, user_agent=None)


@pytest.mark.kiwi_id(2192)
def test_blacklist_key() -> None:
    """黑名单键为 `bms:global:token:blacklist:{jti}`（global 域、小写冒号分隔）。"""
    session = DefaultSessionSecurity(secret_key="s")
    assert session.blacklist_key("123") == f"{BLACKLIST_KEY_PREFIX}:123"
    assert BLACKLIST_KEY_PREFIX == "bms:global:token:blacklist"


@pytest.mark.kiwi_id(2192)
def test_factory_reads_secret_key() -> None:
    """工厂读 `[security].secret_key`；缺省空串仍可构造（prod 由启动校验拦截）。"""
    factory = DefaultSessionSecurityFactory(Settings(security=SecuritySettings(secret_key="secret")))
    assert factory.create().fingerprint(ip="1", user_agent="u") == DefaultSessionSecurity(
        secret_key="secret"
    ).fingerprint(ip="1", user_agent="u")
    assert DefaultSessionSecurityFactory(Settings()).create().new_session_id().isdigit()
