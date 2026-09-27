"""lock 能力域：Redis 分布式锁实现（多副本一致；异常降级进程内 memory）。

- `RedisDistributedLock`（插件名 `redis`，懒建连）：`acquire` 用 `SET key token NX EX ttl`
  （`wait > 0` 时轮询至超时）；`release` / `extend` 用 Lua 脚本**校验令牌**后 `DEL` / `EXPIRE`。
- 降级：Redis 不可用（连接 / 命令异常）时委托 `fallback`（缺省 `MemoryDistributedLock`）并记日志——
  保证互斥不因 Redis 故障整体失效（进程内单副本口径，多副本最终由唯一约束兜底）。
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.logging import get_logger
from bms_core.lock.base import DEFAULT_LOCK_TTL, DEFAULT_WAIT, BaseDistributedLock
from bms_core.lock.memory import MemoryDistributedLock

__all__ = ["RedisDistributedLock"]

_LOGGER = get_logger("bms")

_POLL_INTERVAL = 0.05
"""等待取锁的轮询间隔（秒）。"""

_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
"""释放锁：令牌一致才删除（防误放他人锁）。"""

_EXTEND_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
"""续租：令牌一致才重置 TTL。"""


class RedisDistributedLock(BaseDistributedLock, BaseAsyncResource):
    """Redis 分布式锁（多副本一致；异常降级进程内 memory）。"""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: AsyncRedis | None = None,
        fallback: BaseDistributedLock | None = None,
    ) -> None:
        """初始化（懒建连）。

        Args:
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
            fallback: Redis 异常时的降级锁（缺省新建进程内实现）。
        """
        self._url = url
        self._client = client
        self._fallback = fallback if fallback is not None else MemoryDistributedLock()
        self._degraded = False

    @property
    def client(self) -> AsyncRedis:
        """取异步客户端（懒建）。

        Returns:
            AsyncRedis: 异步客户端实例。
        """
        if self._client is None:
            self._client = AsyncRedis.from_url(self._url or "", decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
        return self._client

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """获取锁（`SET NX EX`；`wait > 0` 轮询至超时；Redis 异常降级 memory）。

        Args:
            key: 锁 key。
            ttl: 锁 TTL（秒）。
            wait: 等待时长（秒）；0 表示不等待。

        Returns:
            str | None: 锁令牌；未取到返回 None。
        """
        seconds = max(1, ttl)
        token = uuid4().hex
        deadline = time.monotonic() + max(0.0, wait)
        while True:
            try:
                acquired = await self.client.set(key, token, nx=True, ex=seconds)  # pyright: ignore[reportUnknownMemberType]
                if self._degraded:
                    self._degraded = False
                    _LOGGER.info("分布式锁 Redis 恢复")
            except Exception as exc:
                if not self._degraded:
                    self._degraded = True
                    _LOGGER.warning("分布式锁 Redis 降级", key=key, error=str(exc))
                return await self._fallback.acquire(key, ttl=ttl, wait=wait)
            if acquired:
                return token
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(min(_POLL_INTERVAL, max(0.0, deadline - time.monotonic())))

    async def release(self, key: str, token: str) -> bool:
        """释放锁（Lua 校验令牌后删除；Redis 异常降级 memory）。

        Args:
            key: 锁 key。
            token: 锁令牌。

        Returns:
            bool: 释放成功 True；非持有者 False。
        """
        try:
            result = await self.client.eval(_RELEASE_LUA, 1, key, token)  # pyright: ignore[reportUnknownMemberType]
            return bool(result)
        except Exception as exc:
            _LOGGER.warning("分布式锁释放降级", key=key, error=str(exc))
            return await self._fallback.release(key, token)

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """续租（Lua 校验令牌后重置 TTL；Redis 异常降级 memory）。

        Args:
            key: 锁 key。
            token: 锁令牌。
            ttl: 新的 TTL（秒）。

        Returns:
            bool: 续租成功 True；非持有者 False。
        """
        seconds = max(1, ttl)
        try:
            result = await self.client.eval(_EXTEND_LUA, 1, key, token, seconds)  # pyright: ignore[reportUnknownMemberType]
            return bool(result)
        except Exception as exc:
            _LOGGER.warning("分布式锁续租降级", key=key, error=str(exc))
            return await self._fallback.extend(key, token, ttl=ttl)

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("分布式锁关闭失败", error=str(exc))
