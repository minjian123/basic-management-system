"""安全原语 · 请求签名测试（Kiwi 43）+ 原语迁移核对（Kiwi 2192）。"""

import hashlib
import hmac

import pytest

from bms_core.core.security import (
    SIGNATURE_ALGORITHM,
    SIGNATURE_HEADER,
    SignatureCodec,
)
from bms_core.security.base import BaseSecurity
from bms_core.security.jwt import JwtTokenCodec
from bms_core.security.null import NullPasswordHasher, NullSessionSecurity, NullTokenCodec
from bms_core.security.pbkdf2 import Pbkdf2PasswordHasher
from bms_core.security.session import DefaultSessionSecurity


@pytest.mark.kiwi_id(2192)
def test_primitives_moved_into_security_package() -> None:
    """安全原语迁入 `bms_core/security/` 能力域：插件基类与实现均纳入 `BaseSecurity` 中间层。"""
    for cls in (
        Pbkdf2PasswordHasher,
        JwtTokenCodec,
        DefaultSessionSecurity,
        NullPasswordHasher,
        NullTokenCodec,
        NullSessionSecurity,
    ):
        assert issubclass(cls, BaseSecurity)
    assert issubclass(SignatureCodec, BaseSecurity)


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
