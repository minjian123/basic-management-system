"""限流能力域测试（Kiwi 2194）：内存 / Redis 固定窗口、重置、降级与关闭。"""

import fakeredis.aioredis
import pytest

from bms_core.core.exceptions import RateLimitError
from bms_core.ratelimit.base import RateLimitRule
from bms_core.ratelimit.memory import MemoryRateLimiter
from bms_core.ratelimit.redis import RedisRateLimiter


@pytest.mark.kiwi_id(2194)
async def test_memory_limiter_window_and_reset() -> None:
    """内存实现：窗口内计数放行、超限拒绝、reset 清零。"""
    limiter = MemoryRateLimiter()
    rule = RateLimitRule(limit=2, window=60)
    first = await limiter.check("k", rule)
    second = await limiter.check("k", rule)
    third = await limiter.check("k", rule)
    assert first.allowed is True and first.remaining == 1
    assert second.allowed is True and second.remaining == 0
    assert third.allowed is False and third.remaining == 0

    await limiter.reset("k")
    assert (await limiter.check("k", rule)).allowed is True
    limiter.clear()
    await limiter.require("k2", RateLimitRule(limit=1, window=60))
    with pytest.raises(RateLimitError):
        await limiter.require("k2", RateLimitRule(limit=1, window=60))


@pytest.mark.kiwi_id(2194)
async def test_redis_limiter_counts_and_reset() -> None:
    """Redis 实现（fakeredis）：计数放行 / 拒绝 / reset。"""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    limiter = RedisRateLimiter(client=client)
    rule = RateLimitRule(limit=2, window=60)
    assert (await limiter.check("rk", rule)).allowed is True
    assert (await limiter.check("rk", rule)).allowed is True
    denied = await limiter.check("rk", rule)
    assert denied.allowed is False and denied.remaining == 0 and denied.reset_after >= 0
    await limiter.reset("rk")
    assert (await limiter.check("rk", rule)).allowed is True
    await limiter.aclose()


@pytest.mark.kiwi_id(2194)
async def test_redis_limiter_degrades_to_memory() -> None:
    """Redis 实现：客户端异常时降级 memory 并记录；reset 亦降级。"""

    class _Broken:
        async def incr(self, key: str) -> int:
            raise RuntimeError("redis down")

        async def delete(self, key: str) -> int:
            raise RuntimeError("redis down")

    fallback = MemoryRateLimiter()
    limiter = RedisRateLimiter(client=_Broken(), fallback=fallback)  # type: ignore[arg-type]
    rule = RateLimitRule(limit=1, window=60)
    assert (await limiter.check("bk", rule)).allowed is True
    assert (await limiter.check("bk", rule)).allowed is False
    await limiter.reset("bk")
    assert (await limiter.check("bk", rule)).allowed is True


@pytest.mark.kiwi_id(2194)
async def test_memory_limiter_window_rollover(monkeypatch: pytest.MonkeyPatch) -> None:
    """内存实现：窗口到期后计数回落（时间推进）。"""

    class _Clock:
        now = 0.0

        def monotonic(self) -> float:
            return self.now

    clock = _Clock()
    monkeypatch.setattr("bms_core.ratelimit.memory.time", clock)
    limiter = MemoryRateLimiter()
    rule = RateLimitRule(limit=1, window=10)
    assert (await limiter.check("k", rule)).allowed is True
    assert (await limiter.check("k", rule)).allowed is False
    clock.now = 20.0
    assert (await limiter.check("k", rule)).allowed is True


@pytest.mark.kiwi_id(2194)
async def test_redis_limiter_lazy_client_and_recovery() -> None:
    """Redis 实现：懒建客户端 + 降级后恢复。"""
    lazy = RedisRateLimiter(url="redis://localhost:6379/0")
    assert lazy.client is not None
    await lazy.aclose()

    class _Broken:
        async def incr(self, key: str) -> int:
            raise RuntimeError("down")

    limiter = RedisRateLimiter(client=_Broken())  # type: ignore[arg-type]
    assert (await limiter.check("k", RateLimitRule(limit=5))).allowed is True

    working = fakeredis.aioredis.FakeRedis(decode_responses=True)
    limiter._client = working  # pyright: ignore[reportPrivateUsage]
    recovered = await limiter.check("k", RateLimitRule(limit=5))
    assert recovered.allowed is True and recovered.reset_after >= 0
    await limiter.aclose()
