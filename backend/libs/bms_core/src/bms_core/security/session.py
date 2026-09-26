"""security 能力域真实实现：会话安全（雪花会话 id / HMAC 指纹 / 黑名单键）。

- `new_session_id`：复用 `core/id.py` 雪花生成器——与 `sys_session.id`、JWT `jti` 同值（单套 id）。
- `fingerprint`：`HMAC-SHA256(secret_key, ip + "\\n" + user_agent)` 十六进制（不落原始 ip / UA；
  设备一致性校验由会话校验链按需比对）。
- `blacklist_key`：`bms:global:token:blacklist:{jti}`（global 域，租户解析前即可校验；见《命名规范》）。
"""

from __future__ import annotations

import hashlib
import hmac

from bms_core.core.config import Settings
from bms_core.core.factory import BasePluginFactory
from bms_core.core.id import id_generator
from bms_core.security.base import BaseSessionSecurity

__all__ = [
    "BLACKLIST_KEY_PREFIX",
    "DefaultSessionSecurity",
    "DefaultSessionSecurityFactory",
]

BLACKLIST_KEY_PREFIX = "bms:global:token:blacklist"
"""会话 / 令牌黑名单键前缀（`bms:global:token:blacklist:{jti}`）。"""


class DefaultSessionSecurity(BaseSessionSecurity):
    """默认会话安全实现（雪花 id + HMAC 指纹 + global 黑名单键）。"""

    plugin_name: str = "default"

    def __init__(self, *, secret_key: str) -> None:
        """初始化（经工厂或显式传参装配；不自动登记为插件——需依赖注入密钥）。

        Args:
            secret_key: 通用密钥（指纹 HMAC；生产由启动校验保证非空）。
        """
        self._secret_key = secret_key

    def new_session_id(self) -> str:
        """生成会话 id（雪花）。

        Returns:
            str: 会话 id（十进制字符串，与 `sys_session.id` 同值）。
        """
        return str(id_generator.next_id())

    def fingerprint(self, *, ip: str | None, user_agent: str | None) -> str:
        """生成会话指纹（HMAC-SHA256 十六进制）。

        Args:
            ip: 客户端 IP（可空）。
            user_agent: 客户端 UA（可空）。

        Returns:
            str: 指纹（小写十六进制）。
        """
        material = f"{ip or ''}\n{user_agent or ''}".encode()
        return hmac.new(self._secret_key.encode("utf-8"), material, hashlib.sha256).hexdigest()

    def blacklist_key(self, session_id: str) -> str:
        """会话黑名单 Redis 键。

        Args:
            session_id: 会话 id（JWT `jti`）。

        Returns:
            str: `bms:global:token:blacklist:{session_id}`。
        """
        return f"{BLACKLIST_KEY_PREFIX}:{session_id}"


class DefaultSessionSecurityFactory(BasePluginFactory[DefaultSessionSecurity]):
    """默认会话安全工厂（读 `[security].secret_key`）。"""

    plugin_key: str = "session_security"
    plugin_name: str = "default"

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 应用配置（`[security]`）。
        """
        self._settings = settings

    def create(self, options: None = None) -> DefaultSessionSecurity:
        """构造默认会话安全实现。

        Args:
            options: 未使用（零参口径）。

        Returns:
            DefaultSessionSecurity: 会话安全实现。
        """
        return DefaultSessionSecurity(secret_key=self._settings.security.secret_key)
