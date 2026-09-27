"""流程状态存储能力域：进程内实现（测试 / 无 Redis 环境降级）。

- `MemoryIdpStateStore`（插件名 `memory`）：进程内字典 + 到期时间，逐条惰性清理；
  `consume` 以 `pop` 实现一次性消费（同进程原子）。
- 仅单副本有效（跨副本一致流程状态须用 `redis` 实现）；与 `RedisIdpStateStore` 同契约。
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from bms_core.idp.state.base import DEFAULT_IDP_STATE_TTL, BaseIdpStateStore

__all__ = ["MemoryIdpStateStore"]


class MemoryIdpStateStore(BaseIdpStateStore):
    """进程内流程状态存储（字典 + 到期时间，单副本口径）。"""

    def __init__(self) -> None:
        """初始化（空存储）。"""
        self._items: dict[str, tuple[dict[str, object], float]] = {}

    async def save(
        self,
        state: str,
        payload: Mapping[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_IDP_STATE_TTL,
    ) -> None:
        """写入 / 覆盖流程状态（TTL 到期时间）。

        Args:
            state: 流程状态（state）。
            payload: 状态数据。
            tenant: 租户编码（进程内实现以 state 为键，忽略租户）。
            ttl: 有效期（秒）。
        """
        self._items[state] = (dict(payload), time.monotonic() + ttl)

    async def consume(self, state: str, *, tenant: str | None = None) -> Mapping[str, object] | None:
        """一次性消费流程状态（取出即删除；不存在 / 已过期返回 None）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码（忽略）。

        Returns:
            Mapping[str, object] | None: 状态数据；不存在 / 已过期返回 None。
        """
        item = self._items.pop(state, None)
        if item is None:
            return None
        payload, expires_at = item
        if expires_at <= time.monotonic():
            return None
        return dict(payload)

    async def delete(self, state: str, *, tenant: str | None = None) -> None:
        """删除流程状态（幂等）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码（忽略）。
        """
        self._items.pop(state, None)

    def clear(self) -> None:
        """清空全部流程状态（测试 / 调试用）。"""
        self._items.clear()
