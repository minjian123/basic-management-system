"""security 能力域 · JWT 令牌编解码测试（Kiwi 2192）：往返 / 过期 / 篡改 / 轮换 / 配置。"""

import pytest
from joserfc.jwk import RSAKey

from bms_core.core.config import SecuritySettings, Settings, TokenKeySettings
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.oauth.keys import TokenKey
from bms_core.security.jwt import JwtTokenCodec, JwtTokenCodecFactory


def _rsa_key(kid: str = "k1") -> TokenKey:
    """生成 RSA 密钥（RS256）。

    Args:
        kid: 密钥标识。

    Returns:
        TokenKey: 密钥材料。
    """
    key = RSAKey.generate_key(2048, private=True)
    return TokenKey(
        kid=kid,
        algorithm="RS256",
        public_key=key.as_pem(private=False).decode(),
        private_key=key.as_pem(private=True).decode(),
    )


def _codec(*keys: TokenKey, active_kid: str = "") -> JwtTokenCodec:
    """构造编解码器。

    Args:
        *keys: 密钥集。
        active_kid: 当前签名密钥。

    Returns:
        JwtTokenCodec: 编解码器。
    """
    return JwtTokenCodec(keys=keys, active_kid=active_kid)


@pytest.mark.kiwi_id(2192)
def test_roundtrip_and_claims() -> None:
    """编解码往返：自动补 `iat`；`expires_in` 补 `exp`；业务声明原样保留。"""
    codec = _codec(_rsa_key(), active_kid="k1")
    token = codec.encode({"sub": "1", "aud": "api", "type": "access"}, expires_in=300)
    claims = codec.decode(token)
    assert claims["sub"] == "1"
    assert claims["aud"] == "api"
    assert claims["type"] == "access"
    assert isinstance(claims["iat"], int)
    assert claims["exp"] == claims["iat"] + 300

    without_exp = codec.decode(codec.encode({"sub": "2"}))
    assert "exp" not in without_exp


@pytest.mark.kiwi_id(2192)
def test_reject_expired_and_tampered() -> None:
    """过期 / 篡改 / 未知 kid / 非 JWT 串 / 非法 exp 一律拒绝（AuthError）。"""
    codec = _codec(_rsa_key(), active_kid="k1")
    with pytest.raises(AuthError):
        codec.decode(codec.encode({"sub": "1"}, expires_in=-60))
    with pytest.raises(AuthError):
        codec.decode(codec.encode({"sub": "1", "exp": "not-a-number"}))

    token = codec.encode({"sub": "1"}, expires_in=300)
    head, payload, signature = token.split(".")
    assert codec.decode(token)["sub"] == "1"
    with pytest.raises(AuthError):
        codec.decode(f"{head}.{payload}.{signature[:-2]}xx")

    other = _codec(_rsa_key("k9"), active_kid="k9")
    with pytest.raises(AuthError):
        codec.decode(other.encode({"sub": "1"}))

    for bad in ("", "not-a-token", "a.b.c"):
        with pytest.raises(AuthError):
            codec.decode(bad)


@pytest.mark.kiwi_id(2192)
def test_rotation_parallel_verify() -> None:
    """轮换：旧 kid 公钥并行验签、`active_kid` 签发、私钥缺失即拒。"""
    keys = (_rsa_key("k1"), _rsa_key("k2"))
    rotating = _codec(*keys, active_kid="k2")
    old_token = _codec(keys[0], active_kid="k1").encode({"sub": "old"})
    new_token = rotating.encode({"sub": "new"})

    assert rotating.decode(old_token)["sub"] == "old"
    assert rotating.decode(new_token)["sub"] == "new"

    rotate_back = _codec(*keys, active_kid="k1")
    assert rotate_back.decode(new_token)["sub"] == "new"

    verifier_only = _codec(_rsa_key("k1"), active_kid="k2")
    with pytest.raises(ConfigError):
        verifier_only.encode({"sub": "x"})
    with pytest.raises(ConfigError):
        _codec(*keys).encode({"sub": "x"})

    single = _codec(_rsa_key("only"))
    assert single.decode(single.encode({"sub": "solo"}))["sub"] == "solo"


@pytest.mark.kiwi_id(2192)
def test_algorithm_whitelist_and_factory() -> None:
    """算法非白名单即拒；工厂读 `[security].keys` / `active_kid`；空密钥集可装配但使用时 fail-closed。"""
    with pytest.raises(ConfigError):
        TokenKey(kid="h1", algorithm="HS256", public_key="x", private_key="y")

    empty = JwtTokenCodecFactory(Settings()).create()
    with pytest.raises(ConfigError):
        empty.encode({"sub": "1"})
    with pytest.raises(AuthError):
        empty.decode("a.b.c")

    with pytest.raises(ConfigError):
        JwtTokenCodecFactory(
            Settings(
                security=SecuritySettings(
                    active_kid="k1",
                    keys={"k1": TokenKeySettings(algorithm="RS256", public_key="", private_key="")},
                )
            )
        ).create()

    key = _rsa_key()
    codec = JwtTokenCodecFactory(
        Settings(
            security=SecuritySettings(
                active_kid="k1",
                keys={
                    "k1": TokenKeySettings(
                        algorithm="RS256",
                        public_key=key.public_key,
                        private_key=key.private_key,
                    )
                },
            )
        )
    ).create()
    assert isinstance(codec, JwtTokenCodec)
