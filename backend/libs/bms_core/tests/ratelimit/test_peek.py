"""限流基座只读计数 `peek` 用例（Kiwi 2208，03_04）。

覆盖：内存与 Redis 实现的 `peek` 不自增 / 重置清零 / 缺省 0；`BaseRateLimiter.peek` 默认 0。
"""

from typing import cast

import pytest

from bms_core.ratelimit.base import BaseRateLimiter, RateLimitDecision, RateLimitRule
from bms_core.ratelimit.memory import MemoryRateLimiter


class _DefaultPeekLimiter(BaseRateLimiter):
    """未覆写 `peek` 的实现（走基类缺省 0）。"""

    async def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """恒放行（占位）。

        Args:
            key: 限流 key。
            rule: 限流规则。

        Returns:
            RateLimitDecision: 放行决策。
        """
        return RateLimitDecision(allowed=True, limit=rule.limit, remaining=rule.limit, reset_after=rule.window)


@pytest.mark.kiwi_id(2208)
async def test_memory_peek_does_not_increment() -> None:
    """内存 `peek`：读当前计数不自增；`reset` 清零；无计数为 0。"""
    limiter = MemoryRateLimiter()
    rule = RateLimitRule(limit=5, window=60)
    assert await limiter.peek("k") == 0
    await limiter.check("k", rule)
    await limiter.check("k", rule)
    assert await limiter.peek("k") == 2
    # 连续 peek 不改变计数
    assert await limiter.peek("k") == 2
    # 再 check 后计数递增
    await limiter.check("k", rule)
    assert await limiter.peek("k") == 3
    await limiter.reset("k")
    assert await limiter.peek("k") == 0


@pytest.mark.kiwi_id(2208)
async def test_redis_peek_roundtrip() -> None:
    """Redis `peek`：读 `GET` 计数不自增；`reset` 清零。"""
    fakeredis = pytest.importorskip("fakeredis")
    from bms_core.ratelimit.redis import RedisRateLimiter

    limiter = RedisRateLimiter(client=fakeredis.aioredis.FakeRedis(decode_responses=True))
    rule = RateLimitRule(limit=5, window=60)
    assert await limiter.peek("k") == 0
    await limiter.check("k", rule)
    await limiter.check("k", rule)
    assert await limiter.peek("k") == 2
    await limiter.reset("k")
    assert await limiter.peek("k") == 0


@pytest.mark.kiwi_id(2208)
async def test_base_peek_default_zero() -> None:
    """基类缺省 `peek` 返回 0（未覆写实现不驱动强制分支）。"""
    assert await _DefaultPeekLimiter().peek("k") == 0


class _BrokenClient:
    """测试替身：`get` 抛异常（触发 Redis 计数读取降级）。"""

    async def get(self, key: str) -> object:
        """抛异常。

        Args:
            key: 缓存 key（忽略）。

        Raises:
            RuntimeError: 模拟 Redis 故障。
        """
        del key
        raise RuntimeError("redis down")


@pytest.mark.kiwi_id(2208)
async def test_redis_peek_degrades() -> None:
    """Redis `peek` 异常时降级 memory（返回 0）。"""
    from redis.asyncio import Redis as AsyncRedis

    from bms_core.ratelimit.redis import RedisRateLimiter

    limiter = RedisRateLimiter(client=cast("AsyncRedis", _BrokenClient()))
    assert await limiter.peek("k") == 0
