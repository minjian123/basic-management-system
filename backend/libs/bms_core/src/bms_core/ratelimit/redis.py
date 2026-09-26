"""限流能力域：Redis 固定窗口限流实现（多副本一致；异常降级 memory）。

- `RedisRateLimiter`（插件名 `redis`）：`INCR` + 首次 `EXPIRE` 的固定窗口计数；TTL 即窗口。
- 降级：Redis 不可用（连接 / 命令异常）时委托 `fallback`（缺省 `MemoryRateLimiter`）判定并记日志——
  保证限流不因 Redis 故障而整体失效（进程内单副本口径）。
"""

from __future__ import annotations

from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.logging import get_logger
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitDecision, RateLimitRule
from bms_core.ratelimit.memory import MemoryRateLimiter

__all__ = ["RedisRateLimiter"]

_LOGGER = get_logger("bms")


class RedisRateLimiter(BaseRateLimiter, BaseAsyncResource):
    """Redis 固定窗口限流（异常降级进程内 memory）。"""

    def __init__(
        self,
        *,
        url: str | None = None,
        client: AsyncRedis | None = None,
        fallback: BaseRateLimiter | None = None,
    ) -> None:
        """初始化（懒建连）。

        Args:
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
            fallback: Redis 异常时的降级限流器（缺省新建进程内实现）。
        """
        self._url = url
        self._client = client
        self._fallback = fallback if fallback is not None else MemoryRateLimiter()
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

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """判定配额（Redis 固定窗口；异常降级 memory）。

        Args:
            key: 限流 key。
            rule: 限流规则（次数 / 窗口）。

        Returns:
            RateLimitDecision: 判定结果。
        """
        window = max(1, rule.window)
        try:
            client = self.client
            count = int(await client.incr(key))  # pyright: ignore[reportUnknownMemberType]
            if count == 1:
                await client.expire(key, window)  # pyright: ignore[reportUnknownMemberType]
            ttl = int(await client.ttl(key))  # pyright: ignore[reportUnknownMemberType]
            if self._degraded:
                self._degraded = False
                _LOGGER.info("限流 Redis 恢复")
            return RateLimitDecision(
                allowed=count <= rule.limit,
                limit=rule.limit,
                remaining=max(0, rule.limit - count),
                reset_after=max(0, ttl),
            )
        except Exception as exc:
            if not self._degraded:
                self._degraded = True
                _LOGGER.warning("限流 Redis 降级", key=key, error=str(exc))
            return await self._fallback.check(key, rule)

    async def reset(self, key: str) -> None:
        """重置配额计数（成功路径清零；Redis 异常降级 memory）。

        Args:
            key: 限流 key。
        """
        try:
            await self.client.delete(key)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("限流计数重置降级", key=key, error=str(exc))
            await self._fallback.reset(key)

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("限流器关闭失败", error=str(exc))
