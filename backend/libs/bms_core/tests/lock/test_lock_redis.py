"""分布式锁 Redis 实现测试（Kiwi 2198）：SET NX / Lua 校验 / 异常降级 memory。"""

from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from bms_core.lock.base import build_lock_key
from bms_core.lock.redis import RedisDistributedLock


class _BrokenClient:
    """恒抛连接异常的客户端替身（验证降级）。"""

    async def set(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")


@pytest.mark.kiwi_id(2198)
async def test_redis_lock_acquire_release_extend() -> None:
    """SET NX 首次成功 / 占用失败；Lua 校验释放与续租。"""
    client = FakeRedis(decode_responses=True)
    lock = RedisDistributedLock(client=cast("Redis", client))
    key = build_lock_key(tenant="demo", resource="jit")

    token = await lock.acquire(key, ttl=30)
    assert token is not None
    assert await lock.acquire(key) is None
    assert await lock.release(key, "wrong") is False
    assert await lock.extend(key, "wrong", ttl=5) is False
    assert await lock.extend(key, token, ttl=5) is True
    assert await lock.acquire(key, wait=0.05) is None
    assert await lock.release(key, token) is True
    reacquired = await lock.acquire(key)
    assert reacquired is not None

    lock._degraded = True  # pyright: ignore[reportPrivateUsage]
    assert await lock.acquire(key) is None  # 占用中：命中断言前 _degraded 复位分支
    assert await lock.release(key, reacquired) is True
    await lock.aclose()


@pytest.mark.kiwi_id(2198)
async def test_redis_lock_fails_closed() -> None:
    """Redis 异常 fail-closed：不降级进程内锁（多副本会失去互斥），抛 10012 / 503（03_04）。"""
    from bms_core.core.exceptions import RedisUnavailableError

    lock = RedisDistributedLock(client=cast("Redis", cast("object", _BrokenClient())))
    key = build_lock_key(tenant="demo", resource="jit")

    with pytest.raises(RedisUnavailableError) as exc_info:
        await lock.acquire(key)
    assert exc_info.value.code == 10012
    assert exc_info.value.http_status == 503
    with pytest.raises(RedisUnavailableError):
        await lock.release(key, "token")
    with pytest.raises(RedisUnavailableError):
        await lock.extend(key, "token", ttl=5)
