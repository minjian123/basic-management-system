"""会话存储能力域：进程内会话存储实现（测试 / 无 Redis 环境降级）。

- `MemorySessionStore`（插件名 `memory`）：进程内字典 + 到期时间，逐条惰性清理。
- 仅单副本有效（跨副本一致会话标记须用 `redis` 实现）；与 `RedisSessionStore` 同契约。
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from bms_core.session.base import DEFAULT_SESSION_TTL, BaseSessionStore

__all__ = ["MemorySessionStore"]


class MemorySessionStore(BaseSessionStore):
    """进程内会话存储（字典 + 到期时间，单副本口径）。"""

    def __init__(self) -> None:
        """初始化（空存储）。"""
        self._items: dict[str, tuple[dict[str, object], float]] = {}
        self._blacklist: dict[str, float] = {}

    async def save(
        self,
        session_id: str,
        payload: Mapping[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_SESSION_TTL,
    ) -> None:
        """写入 / 覆盖会话（TTL 到期时间）。

        Args:
            session_id: 会话 id。
            payload: 会话数据。
            tenant: 租户编码（进程内实现以 `会话 id` 为键，忽略租户）。
            ttl: 有效期（秒，默认 14 天）。
        """
        self._items[session_id] = (dict(payload), time.monotonic() + ttl)

    async def load(self, session_id: str, *, tenant: str | None = None) -> Mapping[str, object] | None:
        """读取会话（不存在 / 已过期返回 None）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（忽略）。

        Returns:
            Mapping[str, object] | None: 会话数据；不存在 / 已过期返回 None。
        """
        item = self._items.get(session_id)
        if item is None:
            return None
        payload, expires_at = item
        if expires_at <= time.monotonic():
            self._items.pop(session_id, None)
            return None
        return dict(payload)

    async def delete(self, session_id: str, *, tenant: str | None = None) -> None:
        """删除会话（幂等）。

        Args:
            session_id: 会话 id。
            tenant: 租户编码（忽略）。
        """
        self._items.pop(session_id, None)

    async def blacklist(self, key: str, *, ttl: int) -> None:
        """写入黑名单标记（TTL 到期时间）。

        Args:
            key: 黑名单键。
            ttl: 有效期（秒）。
        """
        self._blacklist[key] = time.monotonic() + ttl

    async def is_blacklisted(self, key: str) -> bool:
        """判定黑名单（已过期按未命中并清理）。

        Args:
            key: 黑名单键。

        Returns:
            bool: 已入黑名单为 True。
        """
        expires_at = self._blacklist.get(key)
        if expires_at is None:
            return False
        if expires_at <= time.monotonic():
            self._blacklist.pop(key, None)
            return False
        return True

    def clear(self) -> None:
        """清空全部会话与黑名单（测试 / 调试用）。"""
        self._items.clear()
        self._blacklist.clear()
