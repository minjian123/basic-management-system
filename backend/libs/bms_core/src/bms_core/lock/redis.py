"""lock 能力域：Redis 分布式锁实现（多副本一致；异常 fail-closed，不再降级 memory）。

- `RedisDistributedLock`（插件名 `redis`，懒建连）：`acquire` 用 `SET key token NX EX ttl`
  （`wait > 0` 时轮询至超时）；`release` / `extend` 用 Lua 脚本**校验令牌**后 `DEL` / `EXPIRE`。
- **客户端**：统一取进程共享客户端（`bms_core.redis`；禁止各自 `from_url`）。
- **不可用口径（fail-closed，03_04 / 需求 03-5）**：Redis 不可用（未启用 / 连接 / 命令异常）时
  **抛 `RedisUnavailableError`（`10012` / 503）**，**不再降级进程内 `MemoryDistributedLock``**——
  多副本下静默降进程内锁会**真的失去互斥**，属「降级后语义失真」，故不允许降级。
- `fallback` 参数保留以兼容既有构造调用，**不再使用**。
"""

from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.exceptions import RedisUnavailableError
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
        """初始化（客户端惰性取用）。

        Args:
            url: Redis 连接串（保留兼容；连接参数统一取 `[redis]` 与共享客户端）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省取进程共享客户端）。
            fallback: 保留参数（兼容既有构造调用；**不再降级**，Redis 不可用即报 `10012`）。
        """
        self._url = url
        self._client = client
        self._fallback = fallback if fallback is not None else MemoryDistributedLock()
        self._degraded = False

    @property
    def client(self) -> AsyncRedis:
        """取异步客户端（显式注入优先，否则取进程共享客户端）。

        Returns:
            AsyncRedis: 异步客户端实例。

        Raises:
            RedisUnavailableError: Redis 未启用 / 不可用（fail-closed）。
        """
        if self._client is None:
            from bms_core.redis.base import shared_async_client

            self._client = shared_async_client()
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
            except RedisUnavailableError:
                raise
            except Exception as exc:  # Redis 不可用：fail-closed（不降级进程内锁）
                if not self._degraded:
                    self._degraded = True
                    _LOGGER.warning("redis_unavailable", op="lock_acquire", key=key, error=str(exc))
                raise RedisUnavailableError("分布式锁获取失败：Redis 不可用", data={"op": "acquire"}) from exc
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
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed
            _LOGGER.warning("redis_unavailable", op="lock_release", key=key, error=str(exc))
            raise RedisUnavailableError("分布式锁释放失败：Redis 不可用", data={"op": "release"}) from exc

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
        except RedisUnavailableError:
            raise
        except Exception as exc:  # Redis 不可用：fail-closed
            _LOGGER.warning("redis_unavailable", op="lock_extend", key=key, error=str(exc))
            raise RedisUnavailableError("分布式锁续租失败：Redis 不可用", data={"op": "extend"}) from exc

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("分布式锁关闭失败", error=str(exc))
