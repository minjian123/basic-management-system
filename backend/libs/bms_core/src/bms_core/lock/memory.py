"""lock 能力域：进程内分布式锁实现（单副本 / 测试 / Redis 降级兜底）。

- `MemoryDistributedLock`（插件名 `memory`）：进程内字典 + 惰性过期；`acquire` 在 `wait > 0` 时
  按短间隔轮询至超时；`release` / `extend` 按令牌校验，防误放他人锁。
- 与 `RedisDistributedLock` 同契约；单副本口径，多副本一致性由 Redis 实现承担。
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.lock.base import DEFAULT_LOCK_TTL, DEFAULT_WAIT, BaseDistributedLock

__all__ = ["MemoryDistributedLock"]

_POLL_INTERVAL = 0.05
"""等待取锁的轮询间隔（秒）。"""


class MemoryDistributedLock(BaseDistributedLock):
    """进程内分布式锁（单副本口径；惰性过期 + 令牌校验）。"""

    def __init__(self) -> None:
        """初始化（空锁表）。"""
        self._locks: ConcurrentStableDict[str, tuple[str, float]] = ConcurrentStableDict()

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """获取锁（占用则按 `wait` 轮询至超时）。

        Args:
            key: 锁 key。
            ttl: 锁 TTL（秒）；到期自动释放。
            wait: 等待时长（秒）；0 表示不等待。

        Returns:
            str | None: 锁令牌；未取到返回 None。
        """
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            token = self._try_acquire(key, ttl)
            if token is not None:
                return token
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(min(_POLL_INTERVAL, max(0.0, deadline - time.monotonic())))

    async def release(self, key: str, token: str) -> bool:
        """释放锁（按令牌校验，防误放他人锁）。

        Args:
            key: 锁 key。
            token: `acquire` 返回的锁令牌。

        Returns:
            bool: 释放成功 True；非持有者 False。
        """
        entry = self._locks.get(key)
        if entry is None or entry[0] != token:
            return False
        self._locks.delete(key)
        return True

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """续租（按令牌校验后重置 TTL）。

        Args:
            key: 锁 key。
            token: `acquire` 返回的锁令牌。
            ttl: 新的 TTL（秒）。

        Returns:
            bool: 续租成功 True；非持有者 False。
        """
        entry = self._locks.get(key)
        if entry is None or entry[0] != token:
            return False
        self._locks.set(key, (token, time.monotonic() + max(1, ttl)))
        return True

    def clear(self) -> None:
        """清空锁表（测试 / 调试用）。"""
        for key in list(self._locks):
            self._locks.get_and_remove(key)

    def _try_acquire(self, key: str, ttl: int) -> str | None:
        """单次尝试获取锁（惰性过期）。

        Args:
            key: 锁 key。
            ttl: 锁 TTL（秒）。

        Returns:
            str | None: 锁令牌；占用中返回 None。
        """
        now = time.monotonic()
        entry = self._locks.get(key)
        if entry is not None and entry[1] > now:
            return None
        token = uuid4().hex
        self._locks.set(key, (token, now + max(1, ttl)))
        return token
