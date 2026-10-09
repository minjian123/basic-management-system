"""限流能力域：Redis 固定窗口限流实现（多副本一致；异常降级 memory）。

- `RedisRateLimiter`（插件名 `redis`）：`INCR` + 首次 `EXPIRE` 的固定窗口计数；TTL 即窗口。
- **客户端**：统一取进程共享客户端（`bms_core.redis`；禁止各自 `from_url`）。
- **降级口径（03_04 / 需求 03-5 定稿）**：Redis 不可用（连接 / 命令异常）时**保留**委托 `fallback`
  （缺省 `MemoryRateLimiter`，单机计数仍有保护）并记「降级」日志与 `is_degraded` 状态（供指标 / 告警）——
  判据＝「**降级后语义仍正确才允许降级**」；限流若 fail-closed，Redis 抖动会把受保护入口整体拒客。
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
    def is_degraded(self) -> bool:
        """是否处于降级态（Redis 不可用已回落进程内实现；供指标 / 告警消费）。

        Returns:
            bool: 降级中 True。
        """
        return self._degraded

    @property
    def client(self) -> AsyncRedis:
        """取异步客户端（显式注入优先，否则取进程共享客户端）。

        Returns:
            AsyncRedis: 异步客户端实例。

        Raises:
            RedisUnavailableError: Redis 未启用 / 不可用（本域据此降级 fallback）。
        """
        if self._client is None:
            from bms_core.redis.base import shared_async_client

            self._client = shared_async_client()
        return self._client

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """判定配额（Redis 固定窗口；异常降级 memory）。

        Args:
            key: 限流 key。
            rule: 限流规则（次数 / 窗口）。

        Returns:
            RateLimitDecision: 判定结果（Redis 不可用时回落进程内实现，单机计数仍有保护）。
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
                _LOGGER.info("ratelimit_redis_recovered")
            return RateLimitDecision(
                allowed=count <= rule.limit,
                limit=rule.limit,
                remaining=max(0, rule.limit - count),
                reset_after=max(0, ttl),
            )
        except Exception as exc:
            if not self._degraded:
                self._degraded = True
                _LOGGER.warning("ratelimit_redis_degraded", key=key, error=str(exc))
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

    async def peek(self, key: str) -> int:
        """读当前窗口计数（不自增；异常降级 memory）。

        Args:
            key: 限流 key。

        Returns:
            int: 当前窗口计数；无计数 / 非数值返回 0。
        """
        try:
            raw = await self.client.get(key)  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            _LOGGER.warning("限流计数读取降级", key=key, error=str(exc))
            return await self._fallback.peek(key)
        try:
            return int(raw)  # pyright: ignore[reportArgumentType]
        except TypeError, ValueError:
            return 0

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("限流器关闭失败", error=str(exc))
