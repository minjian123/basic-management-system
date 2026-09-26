"""security 能力域真实实现：PBKDF2 口令哈希（标准库，无外部依赖）。

- 哈希串自描述：`pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`（base64 标准字母表，不含 `$`）；
  参数升级（迭代 / 算法 / 盐长变化）由 `needs_rehash` 判定，登录路径据此重算。
- 校验用 `hmac.compare_digest` 常量时间比对；串非法恒 `False`（不抛错，防账号探测）。
- 迭代次数经 `[password_hasher].options.iterations` 覆盖（下限保护 `PBKDF2_MIN_ITERATIONS`）。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.factory import BasePluginFactory
from bms_core.security.base import BasePasswordHasher

__all__ = [
    "PBKDF2_HASH",
    "PBKDF2_ITERATIONS",
    "PBKDF2_KEY_BYTES",
    "PBKDF2_MIN_ITERATIONS",
    "PBKDF2_PREFIX",
    "PBKDF2_SALT_BYTES",
    "Pbkdf2PasswordHasher",
    "Pbkdf2PasswordHasherFactory",
]

PBKDF2_HASH = "sha256"
"""PBKDF2 摘要算法（HMAC-SHA256）。"""

PBKDF2_ITERATIONS = 600_000
"""默认迭代次数（OWASP 对 PBKDF2-HMAC-SHA256 的建议档）。"""

PBKDF2_MIN_ITERATIONS = 100_000
"""迭代次数下限（低于即拒，防配置误设削弱强度）。"""

PBKDF2_SALT_BYTES = 16
"""盐长度（字节）。"""

PBKDF2_KEY_BYTES = 32
"""派生密钥长度（字节）。"""

PBKDF2_PREFIX = f"pbkdf2_{PBKDF2_HASH}"
"""哈希串算法前缀（自描述）。"""

_SEPARATOR = "$"
"""哈希串字段分隔符。"""


class Pbkdf2PasswordHasher(BasePasswordHasher):
    """PBKDF2-HMAC-SHA256 口令哈希实现。"""

    plugin_name: str = "pbkdf2"

    def __init__(self, *, iterations: int) -> None:
        """初始化（经工厂或显式传参装配；不自动登记为插件——需依赖注入迭代次数）。

        Args:
            iterations: 迭代次数（不得低于 `PBKDF2_MIN_ITERATIONS`）。

        Raises:
            ConfigError: 迭代次数低于下限（40001）。
        """
        if iterations < PBKDF2_MIN_ITERATIONS:
            raise ConfigError(f"PBKDF2 迭代次数过低：{iterations}（下限 {PBKDF2_MIN_ITERATIONS}）")
        self._iterations = iterations

    def hash(self, password: str) -> str:
        """生成自描述哈希串。

        Args:
            password: 口令明文。

        Returns:
            str: `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`。
        """
        salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
        digest = self._derive(password, salt, self._iterations)
        return _SEPARATOR.join((PBKDF2_PREFIX, str(self._iterations), _b64(salt), _b64(digest)))

    def verify(self, password: str, hashed: str) -> bool:
        """校验口令（常量时间比对；串非法恒 `False`）。

        Args:
            password: 口令明文。
            hashed: 存储的哈希串。

        Returns:
            bool: 校验通过为 True。
        """
        parsed = _parse(hashed)
        if parsed is None:
            return False
        prefix, iterations, salt, digest = parsed
        if prefix != PBKDF2_PREFIX or iterations <= 0 or len(salt) != PBKDF2_SALT_BYTES:
            return False
        candidate = self._derive(password, salt, iterations)
        return hmac.compare_digest(candidate, digest)

    def needs_rehash(self, hashed: str) -> bool:
        """哈希串是否需按当前参数重算。

        Args:
            hashed: 存储的哈希串。

        Returns:
            bool: 算法 / 迭代 / 盐长 / 摘要长不一致或串非法为 True。
        """
        parsed = _parse(hashed)
        if parsed is None:
            return True
        prefix, iterations, salt, digest = parsed
        return (
            prefix != PBKDF2_PREFIX
            or iterations != self._iterations
            or len(salt) != PBKDF2_SALT_BYTES
            or len(digest) != PBKDF2_KEY_BYTES
        )

    @staticmethod
    def _derive(password: str, salt: bytes, iterations: int) -> bytes:
        """派生密钥（PBKDF2-HMAC-SHA256）。

        Args:
            password: 口令明文。
            salt: 盐。
            iterations: 迭代次数。

        Returns:
            bytes: 派生密钥。
        """
        return hashlib.pbkdf2_hmac(
            PBKDF2_HASH,
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=PBKDF2_KEY_BYTES,
        )


class Pbkdf2PasswordHasherFactory(BasePluginFactory[Pbkdf2PasswordHasher]):
    """PBKDF2 哈希工厂（读 `[password_hasher].options.iterations`）。"""

    plugin_key: str = "password_hasher"
    plugin_name: str = "pbkdf2"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[password_hasher]` 选择与选项）。
        """
        self._settings = settings

    def create(self, options: None = None) -> Pbkdf2PasswordHasher:
        """构造 PBKDF2 哈希实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            Pbkdf2PasswordHasher: 哈希实现。

        Raises:
            ConfigError: 迭代次数非法（40001）。
        """
        raw = self._settings.password_hasher.options.get("iterations", PBKDF2_ITERATIONS)
        try:
            iterations = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"PBKDF2 迭代次数配置非法：{raw!r}") from exc
        return Pbkdf2PasswordHasher(iterations=iterations)


def _b64(value: bytes) -> str:
    """base64 编码（标准字母表，无换行）。

    Args:
        value: 原始字节。

    Returns:
        str: base64 串。
    """
    return base64.b64encode(value).decode("ascii")


def _parse(hashed: str) -> tuple[str, int, bytes, bytes] | None:
    """解析哈希串（非法返回 None，不抛错）。

    Args:
        hashed: 哈希串。

    Returns:
        tuple[str, int, bytes, bytes] | None: (`prefix`, `iterations`, `salt`, `digest`)；非法为 None。
    """
    parts = hashed.split(_SEPARATOR)
    if len(parts) != 4:
        return None
    prefix, iterations_raw, salt_raw, digest_raw = parts
    try:
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_raw.encode("ascii"), validate=True)
        digest = base64.b64decode(digest_raw.encode("ascii"), validate=True)
    except (ValueError, binascii.Error):
        return None
    return prefix, iterations, salt, digest
