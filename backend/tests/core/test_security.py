"""安全基座结构占位测试（Kiwi 22）。"""

import pytest

from app.core.base import BaseObject
from app.core.security import BaseSecurity, PasswordHasher, SessionSecurity, TokenCodec


@pytest.mark.kiwi_id(22)
def test_inheritance() -> None:
    """安全原语纳入 L0：原语类 → BaseSecurity → BaseObject。"""
    assert issubclass(BaseSecurity, BaseObject)
    for cls in (PasswordHasher, TokenCodec, SessionSecurity):
        assert issubclass(cls, BaseSecurity)


@pytest.mark.kiwi_id(22)
def test_constructible() -> None:
    """原语类可实例化（构造可解析、应用可启动）。"""
    for cls in (PasswordHasher, TokenCodec, SessionSecurity):
        assert isinstance(cls(), BaseSecurity)


@pytest.mark.kiwi_id(22)
def test_placeholder_raises() -> None:
    """占位实现一律抛 NotImplementedError（防误用）。"""
    hasher = PasswordHasher()
    with pytest.raises(NotImplementedError):
        hasher.hash("secret")
    with pytest.raises(NotImplementedError):
        hasher.verify("secret", "hashed")

    codec = TokenCodec()
    with pytest.raises(NotImplementedError):
        codec.encode({"sub": "1"})
    with pytest.raises(NotImplementedError):
        codec.decode("token")

    session = SessionSecurity()
    with pytest.raises(NotImplementedError):
        session.new_session_id()
    with pytest.raises(NotImplementedError):
        session.fingerprint(ip=None, user_agent=None)
    with pytest.raises(NotImplementedError):
        session.blacklist_key("sid")
