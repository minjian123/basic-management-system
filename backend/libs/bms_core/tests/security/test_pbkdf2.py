"""security 能力域 · PBKDF2 口令哈希测试（Kiwi 2192）：格式 / 校验 / 重哈希 / 配置。"""

import pytest

from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import ConfigError
from bms_core.security.pbkdf2 import (
    PBKDF2_ITERATIONS,
    PBKDF2_MIN_ITERATIONS,
    PBKDF2_PREFIX,
    Pbkdf2PasswordHasher,
    Pbkdf2PasswordHasherFactory,
)

_FAST_ITERATIONS = PBKDF2_MIN_ITERATIONS


def _hasher() -> Pbkdf2PasswordHasher:
    """构造低迭代哈希器（测试提速；不低于下限）。

    Returns:
        Pbkdf2PasswordHasher: 哈希器。
    """
    return Pbkdf2PasswordHasher(iterations=_FAST_ITERATIONS)


@pytest.mark.kiwi_id(2192)
def test_hash_format_and_verify() -> None:
    """哈希串自描述；正确口令通过、错误口令拒绝、非法串恒 False。"""
    hasher = _hasher()
    hashed = hasher.hash("S3cret!密码")
    parts = hashed.split("$")
    assert len(parts) == 4
    assert parts[0] == PBKDF2_PREFIX
    assert int(parts[1]) == _FAST_ITERATIONS

    assert hasher.verify("S3cret!密码", hashed) is True
    assert hasher.verify("wrong", hashed) is False
    for malformed in ("", "not-a-hash", "pbkdf2_sha256$100000$!!!$!!!", "pbkdf2_sha256$abc$AA==$AA=="):
        assert hasher.verify("S3cret!密码", malformed) is False
    assert hasher.verify("S3cret!密码", "other_algo$100000$AA==$AA==") is False
    assert hasher.verify("S3cret!密码", f"{PBKDF2_PREFIX}$0$AA==$AA==") is False

    assert hasher.hash("same") != hasher.hash("same")


@pytest.mark.kiwi_id(2192)
def test_needs_rehash() -> None:
    """迭代 / 算法 / 盐长 / 摘要长变化与串非法 → 需重算。"""
    hasher = _hasher()
    assert hasher.needs_rehash(hasher.hash("x")) is False
    assert hasher.needs_rehash(Pbkdf2PasswordHasher(iterations=PBKDF2_ITERATIONS).hash("x")) is True
    assert hasher.needs_rehash("bad") is True
    assert hasher.needs_rehash(f"other${_FAST_ITERATIONS}$AA==$AA==") is True


@pytest.mark.kiwi_id(2192)
def test_iterations_lower_bound() -> None:
    """迭代次数低于下限即拒。"""
    with pytest.raises(ConfigError):
        Pbkdf2PasswordHasher(iterations=PBKDF2_MIN_ITERATIONS - 1)


@pytest.mark.kiwi_id(2192)
def test_factory_reads_options() -> None:
    """工厂读 `[password_hasher].options.iterations`；非法配置即拒。"""
    factory = Pbkdf2PasswordHasherFactory(
        Settings(password_hasher=PluginSelection(provider="pbkdf2", options={"iterations": _FAST_ITERATIONS}))
    )
    hasher = factory.create()
    assert int(hasher.hash("x").split("$")[1]) == _FAST_ITERATIONS
    assert int(Pbkdf2PasswordHasherFactory(Settings()).create().hash("x").split("$")[1]) == PBKDF2_ITERATIONS

    for bad in ("abc", 0):
        with pytest.raises(ConfigError):
            Pbkdf2PasswordHasherFactory(
                Settings(password_hasher=PluginSelection(provider="pbkdf2", options={"iterations": bad}))
            ).create()
