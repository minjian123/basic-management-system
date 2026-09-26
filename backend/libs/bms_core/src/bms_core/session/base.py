"""会话存储能力域：会话存取契约（真实 Redis + `sys_session` 随认证阶段回补）。

- `DEFAULT_SESSION_TTL`：默认会话 TTL（秒，14 天，与 refresh token 对齐）。
- `BaseSessionStore`：能力域中间层契约（`key = "session_store"`）——异步 `save` / `load` / `delete`。
- `get_session_store`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：`session_id` 对应架构「会话管理」的会话 id（真实 key `bms:{租户}:sess:{session_id}` 由实现拼接）；
`load` 未命中返回 None（与会话不存在 = 已踢出 / 登出语义一致）。强制踢出、多端会话上限、`sys_session`
持久化归认证阶段上层；本契约只落会话存取原语（客户端侧）。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import cast

from fastapi import Request

from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "DEFAULT_SESSION_TTL",
    "SESSION_KEY_PREFIX",
    "BaseSessionStore",
    "build_session_key",
    "get_session_store",
]

DEFAULT_SESSION_TTL = 1209600
"""默认会话 TTL（秒，14 天，与 refresh token 有效期对齐）。"""

SESSION_KEY_PREFIX = "bms"
"""会话标记键前缀（`bms:{租户}:sess:{会话 id}`，与缓存 / 锁 / 限流键同前缀）。"""


def build_session_key(session_id: str, *, tenant: str | None = None) -> str:
    """构建会话标记 Redis 键（规范 `bms:{租户}:sess:{会话 id}`）。

    Args:
        session_id: 会话 id（JWT `jti`，与 `sys_session.session_id` 同值）。
        tenant: 租户编码；None 表示无租户维度（global 域）。

    Returns:
        str: 会话标记键。
    """
    return f"{SESSION_KEY_PREFIX}:{tenant or 'global'}:sess:{session_id}"


class BaseSessionStore(BasePluggable, ABC):
    """会话存储契约：写入 / 读取 / 删除。"""

    key: str = "session_store"
    plugin_key: str = "session_store"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def save(
        self,
        session_id: str,
        payload: Mapping[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """写入 / 覆盖会话（真实实现落 `sys_session` + Redis 标记）。

        Args:
            session_id: 会话 id。
            payload: 会话数据。
            tenant: 租户编码（定位 `bms:{租户}:sess:{id}` 键；None 为 global 域）。
            ttl: 有效期（秒，默认 `DEFAULT_SESSION_TTL`）。
        """

    @abstractmethod
    async def load(self, session_id: str, *, tenant: str | None = None) -> Mapping[str, object] | None:
        """读取会话（不存在返回 None）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（定位键；None 为 global 域）。

        Returns:
            Mapping[str, object] | None: 会话数据；不存在返回 None。
        """

    @abstractmethod
    async def delete(self, session_id: str, *, tenant: str | None = None) -> None:
        """删除会话（幂等，不存在不报错）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（定位键；None 为 global 域）。
        """

    @abstractmethod
    async def blacklist(self, key: str, *, ttl: int) -> None:
        """写入令牌黑名单标记（登出 / 强踢；键由会话安全域派生）。

        Args:
            key: 黑名单键（`BaseSessionSecurity.blacklist_key(jti)`）。
            ttl: 有效期（秒；短 TTL，覆盖 refresh 剩余生命周期）。
        """

    @abstractmethod
    async def is_blacklisted(self, key: str) -> bool:
        """判定令牌是否已入黑名单。

        Args:
            key: 黑名单键（`BaseSessionSecurity.blacklist_key(jti)`）。

        Returns:
            bool: 已入黑名单为 True。
        """


def get_session_store(request: Request) -> BaseSessionStore:
    """取应用级会话存储（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseSessionStore: 应用装配的会话存储实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseSessionStore",
        resolve_plugin(
            "session_store",
            settings.session_store.provider,
            expected_version=BaseSessionStore.contract_version,
        ),
    )
