"""Redis 统一客户端用例（`03_04` 补齐）：真实实现懒建 / 共享登记与缺省实现 fail-closed。

覆盖 `bms_core/redis/redis.py`（`RedisRedisClient`）、`bms_core/redis/null.py`（`NullRedisClient`）
与 `bms_core/redis/base.py` 的共享客户端取用（未登记回落缺省实现）。
"""

from __future__ import annotations

from typing import Any, cast

import fakeredis
import fakeredis.aioredis
import pytest

from bms_core.core.exceptions import RedisUnavailableError
from bms_core.redis.base import (
    DEFAULT_KEY_PREFIX,
    clear_shared_redis_client,
    shared_async_client,
    shared_redis_client,
    shared_sync_client,
)
from bms_core.redis.null import NullRedisClient
from bms_core.redis.redis import RedisRedisClient


def _client(*, pool_size: int = 0, key_prefix: str = DEFAULT_KEY_PREFIX) -> RedisRedisClient:
    """构造注入 fakeredis 的 Redis 统一客户端。

    Args:
        pool_size: 连接池上限。
        key_prefix: 键前缀。

    Returns:
        RedisRedisClient: 统一客户端。
    """
    return RedisRedisClient(
        "redis://localhost:6379/0",
        pool_size=pool_size,
        key_prefix=key_prefix,
        sync_client=fakeredis.FakeRedis(decode_responses=True),
        async_client=fakeredis.aioredis.FakeRedis(decode_responses=True),
    )


def test_null_client_fails_closed() -> None:
    """缺省实现：取客户端 / 探测即抛 `RedisUnavailableError`（不静默降级）。"""
    client = NullRedisClient()
    assert client.url == ""
    assert client.key_prefix == DEFAULT_KEY_PREFIX
    with pytest.raises(RedisUnavailableError):
        client.sync_client()
    with pytest.raises(RedisUnavailableError):
        client.async_client()


async def test_null_client_ping_fails_closed() -> None:
    """缺省实现 `ping` 恒失败。"""
    with pytest.raises(RedisUnavailableError):
        await NullRedisClient().ping()


def test_shared_client_falls_back_to_null_and_sync_raises() -> None:
    """共享客户端未登记 → 回落缺省实现；取同步客户端即报 10012。"""
    clear_shared_redis_client()
    assert isinstance(shared_redis_client(), NullRedisClient)
    with pytest.raises(RedisUnavailableError):
        shared_sync_client()


def test_client_properties_and_pool_bounds() -> None:
    """连接串 / 键前缀 / 连接池上限映射（0 = 客户端默认 → None）。"""
    client = _client(pool_size=0)
    assert client.url == "redis://localhost:6379/0"
    assert client.key_prefix == DEFAULT_KEY_PREFIX
    assert client._max_connections is None

    assert _client(pool_size=8)._max_connections == 8
    assert _client(key_prefix="x:").key_prefix == "x:"


def test_client_lazily_builds_real_clients() -> None:
    """未注入客户端时按 `[redis]` 惰性建连（不在 `setup()` 建连）。"""
    client = RedisRedisClient(
        "redis://localhost:6379/0",
        db=2,
        pool_size=4,
        socket_timeout_ms=1,
        socket_connect_timeout_ms=1,
        health_check_interval_s=0,
    )
    assert client.sync_client() is client.sync_client()
    assert client.async_client() is client.async_client()


async def test_shared_async_client_uses_registered_client() -> None:
    """`shared_async_client()` 经共享客户端取异步实例。"""
    client = _client()
    await client.setup()
    assert shared_async_client() is client.async_client()


async def test_setup_registers_shared_and_aclose_clears() -> None:
    """`setup()` 登记为进程共享客户端；`aclose()` 释放并清登记（幂等）。"""
    client = _client()
    await client.setup()
    assert shared_redis_client() is client

    await client.ping()
    await client.aclose()
    assert not isinstance(shared_redis_client(), RedisRedisClient)

    # 已释放后再次释放不报错。
    await client.aclose()


async def test_aclose_without_clients_is_noop() -> None:
    """无客户端时 `aclose` 空操作（不抛错）。"""
    client = RedisRedisClient("redis://localhost:6379/0")
    await client.aclose()
    assert cast("Any", client) is not None
