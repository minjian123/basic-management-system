"""安全基座测试（Kiwi 33）：结构占位口径 + 签名原语真实实现（Kiwi 43）。"""

import hashlib
import hmac

import pytest

from bms_core.core.base import BaseObject
from bms_core.core.security import (
    SIGNATURE_ALGORITHM,
    SIGNATURE_HEADER,
    BaseSecurity,
    PasswordHasher,
    SessionSecurity,
    SignatureCodec,
    TokenCodec,
)


@pytest.mark.kiwi_id(33)
def test_inheritance() -> None:
    """安全原语纳入 L0：原语类 → BaseSecurity → BaseObject。"""
    assert issubclass(BaseSecurity, BaseObject)
    for cls in (PasswordHasher, TokenCodec, SessionSecurity, SignatureCodec):
        assert issubclass(cls, BaseSecurity)


@pytest.mark.kiwi_id(33)
def test_constructible() -> None:
    """原语类可实例化（构造可解析、应用可启动）。"""
    for cls in (PasswordHasher, TokenCodec, SessionSecurity, SignatureCodec):
        assert isinstance(cls(), BaseSecurity)


@pytest.mark.kiwi_id(33)
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


@pytest.mark.kiwi_id(43)
def test_signature_constants() -> None:
    """签名头与算法常量口径。"""
    assert SIGNATURE_HEADER == "X-Signature"
    assert SIGNATURE_ALGORITHM == "sha256"


@pytest.mark.kiwi_id(43)
def test_signature_payload_and_roundtrip() -> None:
    """串料口径（方法大写 / 换行分隔）与 HMAC-SHA256 往返一致（含 hex 小写与容错比对）。"""
    codec = SignatureCodec()
    payload = codec.build_payload(
        method="post",
        path="/api/open/orders",
        timestamp=1800000000,
        nonce="n1",
        body='{"a":1}',
    )
    assert payload == 'POST\n/api/open/orders\n1800000000\nn1\n{"a":1}'
    assert codec.build_payload(method="GET", path="/api/open/x", timestamp=1, nonce="n") == "GET\n/api/open/x\n1\nn\n"

    signature = codec.sign(secret="s", method="POST", path="/api/open/orders", timestamp=1800000000, nonce="n1")
    expected = hmac.new(b"s", b"POST\n/api/open/orders\n1800000000\nn1\n", hashlib.sha256).hexdigest()
    assert signature == expected
    assert signature == signature.lower()
    assert len(signature) == 64

    assert codec.verify(
        secret="s",
        signature=signature.upper(),
        method="POST",
        path="/api/open/orders",
        timestamp=1800000000,
        nonce="n1",
    )
    assert not codec.verify(
        secret="other",
        signature=signature,
        method="POST",
        path="/api/open/orders",
        timestamp=1800000000,
        nonce="n1",
    )
    assert not codec.verify(
        secret="s",
        signature=signature,
        method="POST",
        path="/api/open/orders",
        timestamp=1800000000,
        nonce="n1",
        body='{"a":2}',
    )
