"""流程状态存储能力域：进程内实现（测试 / 无 Redis 环境降级）。

- `MemoryIdpStateStore`（插件名 `memory`）：进程内字典 + 到期时间，逐条惰性清理；
  `consume` 以 `pop` 实现一次性消费（同进程原子）。
- 仅单副本有效（跨副本一致流程状态须用 `redis` 实现）；与 `RedisIdpStateStore` 同契约。
"""

from __future__ import annotations

import time

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.idp.state.base import (
    DEFAULT_IDP_STATE_TTL,
    IDP_STATE_DEFAULT_NAMESPACE,
    BaseIdpStateStore,
    build_idp_state_key,
)

__all__ = ["MemoryIdpStateStore"]


class MemoryIdpStateStore(BaseIdpStateStore):
    """进程内流程状态存储（字典 + 到期时间，单副本口径）。"""

    def __init__(self) -> None:
        """初始化（空存储）。"""
        self._items: ConcurrentStableDict[str, tuple[ConcurrentStableDict[str, object], float]] = ConcurrentStableDict()

    async def save(
        self,
        state: str,
        payload: ConcurrentStableDict[str, object],
        *,
        tenant: str | None = None,
        ttl: int = DEFAULT_IDP_STATE_TTL,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """写入 / 覆盖流程状态（TTL 到期时间）。

        Args:
            state: 流程状态（state）。
            payload: 状态数据。
            tenant: 租户编码（并入键，与 Redis 实现同键形）。
            ttl: 有效期（秒）。
            namespace: 命名空间（默认 `idpstate`）。
        """
        self._items.set(
            build_idp_state_key(state, tenant=tenant, namespace=namespace),
            (ConcurrentStableDict(payload), time.monotonic() + ttl),
        )

    async def consume(
        self,
        state: str,
        *,
        tenant: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> ConcurrentStableDict[str, object] | None:
        """一次性消费流程状态（取出即删除；不存在 / 已过期返回 None）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码（并入键）。
            namespace: 命名空间（默认 `idpstate`）。

        Returns:
            ConcurrentStableDict[str, object] | None: 状态数据；不存在 / 已过期返回 None。
        """
        item = self._items.get_and_remove(build_idp_state_key(state, tenant=tenant, namespace=namespace))
        if item is None:
            return None
        payload, expires_at = item
        if expires_at <= time.monotonic():
            return None
        return payload

    async def delete(
        self,
        state: str,
        *,
        tenant: str | None = None,
        namespace: str = IDP_STATE_DEFAULT_NAMESPACE,
    ) -> None:
        """删除流程状态（幂等）。

        Args:
            state: 流程状态（state）。
            tenant: 租户编码（并入键）。
            namespace: 命名空间（默认 `idpstate`）。
        """
        self._items.get_and_remove(build_idp_state_key(state, tenant=tenant, namespace=namespace))

    def clear(self) -> None:
        """清空全部流程状态（测试 / 调试用）。"""
        for key in self._items:
            self._items.get_and_remove(key)
