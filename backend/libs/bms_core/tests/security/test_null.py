"""security 能力域 · Null 实现 fail-closed 测试（Kiwi 2192）：配置缺失不误放行。"""

import pytest

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.security.base import BasePasswordHasher, BaseSessionSecurity, BaseTokenCodec
from bms_core.security.null import NullPasswordHasher, NullSessionSecurity, NullTokenCodec


@pytest.mark.kiwi_id(2192)
def test_inheritance_and_placeholder() -> None:
    """Null 实现继承对应契约与 Null Object 标记（可实例化、describe 标注占位）。"""
    for cls, base in (
        (NullPasswordHasher, BasePasswordHasher),
        (NullTokenCodec, BaseTokenCodec),
        (NullSessionSecurity, BaseSessionSecurity),
    ):
        assert issubclass(cls, base)
        assert issubclass(cls, BaseNullObject)
        instance = cls()
        assert instance.placeholder is True
        assert "占位实现" in instance.describe()


@pytest.mark.kiwi_id(2192)
def test_password_hasher_fail_closed() -> None:
    """口令哈希：生成即拒、校验恒拒绝、重算恒要求。"""
    hasher = NullPasswordHasher()
    with pytest.raises(ConfigError):
        hasher.hash("x")
    assert hasher.verify("x", "y") is False
    assert hasher.needs_rehash("y") is True


@pytest.mark.kiwi_id(2192)
def test_token_codec_fail_closed() -> None:
    """令牌编解码：签发即拒、校验一律视为非法令牌。"""
    codec = NullTokenCodec()
    with pytest.raises(ConfigError):
        codec.encode({"sub": "1"})
    with pytest.raises(AuthError):
        codec.decode("token")


@pytest.mark.kiwi_id(2192)
def test_session_security_fail_closed() -> None:
    """会话安全：三方法均拒（未配置真实实现即拒绝）。"""
    session = NullSessionSecurity()
    with pytest.raises(ConfigError):
        session.new_session_id()
    with pytest.raises(ConfigError):
        session.fingerprint(ip=None, user_agent=None)
    with pytest.raises(ConfigError):
        session.blacklist_key("sid")
