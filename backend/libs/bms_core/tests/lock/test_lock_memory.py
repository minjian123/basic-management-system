"""分布式锁进程内实现测试（Kiwi 2198）：获取 / 令牌校验 / 惰性过期 / wait 轮询 / 清空。"""

import time

import pytest

from bms_core.lock.base import build_lock_key
from bms_core.lock.memory import MemoryDistributedLock


@pytest.mark.kiwi_id(2198)
async def test_memory_lock_acquire_release_extend() -> None:
    """首次获取成功 / 二次失败；释放与续租令牌校验（错令牌不生效）。"""
    lock = MemoryDistributedLock()
    key = build_lock_key(tenant="demo", resource="jit")

    token = await lock.acquire(key)
    assert token is not None
    assert await lock.acquire(key) is None
    assert await lock.release(key, "wrong-token") is False
    assert await lock.extend(key, "wrong-token", ttl=60) is False
    assert await lock.extend(key, token, ttl=60) is True
    assert await lock.release(key, token) is True

    reacquired = await lock.acquire(key)
    assert reacquired is not None and reacquired != token


@pytest.mark.kiwi_id(2198)
async def test_memory_lock_lazy_expiry_and_wait() -> None:
    """惰性过期：到期后可再取；wait 轮询超时无锁返回 None。"""
    lock = MemoryDistributedLock()
    key = build_lock_key(tenant="demo", resource="jit")
    token = await lock.acquire(key, ttl=1)
    assert token is not None
    lock._locks[key] = (token, time.monotonic() - 1)  # pyright: ignore[reportPrivateUsage]
    assert await lock.acquire(key) is not None

    assert await lock.acquire(key, wait=0.1) is None
    lock.clear()
    assert await lock.acquire(key) is not None
