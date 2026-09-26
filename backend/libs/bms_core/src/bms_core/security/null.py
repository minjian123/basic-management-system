"""security 能力域缺省实现（Null Object）：**fail-closed**——配置缺失不误放行。

- `NullPasswordHasher`：`hash` 抛 `ConfigError`；`verify` 恒 `False`；`needs_rehash` 恒 `True`。
- `NullTokenCodec`：`encode` 抛 `ConfigError`；`decode` 抛 `AuthError`。
- `NullSessionSecurity`：三方法均抛 `ConfigError`（未配置真实实现即拒绝）。

口径：与 `NullCaptcha` / `NullMasker` 的「恒定通过」不同，安全原语的 Null 不得造成放行——
`[password_hasher]` / `[token_codec]` / `[session_security]` 未显式配置真实实现时，认证链路应显式失败。
"""

from __future__ import annotations

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import AuthError, ConfigError
from bms_core.security.base import (
    BasePasswordHasher,
    BaseSessionSecurity,
    BaseTokenCodec,
)

__all__ = [
    "NullPasswordHasher",
    "NullSessionSecurity",
    "NullTokenCodec",
]

_MISSING_IMPLEMENTATION = "安全实现未配置（{plugin_key} 未选定真实实现）"


class NullPasswordHasher(BasePasswordHasher, BaseNullObject):
    """口令哈希缺省实现（fail-closed）。"""

    def hash(self, password: str) -> str:
        """拒绝生成哈希。

        Args:
            password: 口令明文（未使用）。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError(_MISSING_IMPLEMENTATION.format(plugin_key="password_hasher"))

    def verify(self, password: str, hashed: str) -> bool:
        """恒定拒绝（不泄露任何信息）。

        Args:
            password: 口令明文（未使用）。
            hashed: 哈希串（未使用）。

        Returns:
            bool: False。
        """
        return False

    def needs_rehash(self, hashed: str) -> bool:
        """恒定要求重算（占位串一律视为过期）。

        Args:
            hashed: 哈希串（未使用）。

        Returns:
            bool: True。
        """
        return True


class NullTokenCodec(BaseTokenCodec, BaseNullObject):
    """令牌编解码缺省实现（fail-closed）。"""

    def encode(self, claims: dict[str, object], *, expires_in: int | None = None) -> str:
        """拒绝签发。

        Args:
            claims: 声明（未使用）。
            expires_in: 有效期（未使用）。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError(_MISSING_IMPLEMENTATION.format(plugin_key="token_codec"))

    def decode(self, token: str) -> dict[str, object]:
        """拒绝校验（一律视为非法令牌）。

        Args:
            token: JWT 紧凑串（未使用）。

        Raises:
            AuthError: 恒定失败（20001 / 401）。
        """
        raise AuthError("令牌校验失败")


class NullSessionSecurity(BaseSessionSecurity, BaseNullObject):
    """会话安全缺省实现（fail-closed）。"""

    def new_session_id(self) -> str:
        """拒绝生成会话 id。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError(_MISSING_IMPLEMENTATION.format(plugin_key="session_security"))

    def fingerprint(self, *, ip: str | None, user_agent: str | None) -> str:
        """拒绝生成指纹。

        Args:
            ip: 客户端 IP（未使用）。
            user_agent: 客户端 UA（未使用）。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError(_MISSING_IMPLEMENTATION.format(plugin_key="session_security"))

    def blacklist_key(self, session_id: str) -> str:
        """拒绝生成黑名单键。

        Args:
            session_id: 会话 id（未使用）。

        Raises:
            ConfigError: 未配置真实实现（40001）。
        """
        raise ConfigError(_MISSING_IMPLEMENTATION.format(plugin_key="session_security"))
