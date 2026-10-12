"""Redis 缓存 Region 用例（`03_04` 补齐）：同步 / 异步契约、抖动 TTL、互斥锁与降级。

覆盖 `bms_core/cache/redis.py`：`RedisCacheRegion` 属性与惰性客户端、`ttl_with_jitter`、
同步 / 异步读写删与版本号、`asetnx` / `arelease_lock`、`clear` / `setup` / `aclose`，
以及客户端异常时的**降级**语义（读未命中 / 写空操作 / 锁放行）。
"""

from __future__ import annotations

import json
from typing import Any, cast

import fakeredis
import fakeredis.aioredis

from bms_core.cache.redis import RedisCacheRegion, _load, _to_int  # pyright: ignore[reportPrivateUsage]
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.redis.base import clear_shared_redis_client, set_shared_redis_client
from bms_core.redis.redis import RedisRedisClient


class _Broken:
    """故障客户端替身：任何方法调用即抛错。"""

    def __getattr__(self, name: str) -> Any:
        """返回一个恒抛错的属性。

        Args:
            name: 属性名。

        Returns:
            Any: 调用即抛错的替身。
        """

        def _boom(*_args: object, **_kwargs: object) -> Any:
            raise RuntimeError(f"boom:{name}")

        return _boom


def _region(**overrides: object) -> RedisCacheRegion:
    """构造共享 FakeServer 的 Redis Region。

    Args:
        overrides: 构造参数覆写。

    Returns:
        RedisCacheRegion: 缓存 Region。
    """
    fake: Any = fakeredis
    server = fake.FakeServer()
    params: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
    params.set("domain", "demo")
    params.set("sync_client", fake.FakeRedis(server=server, decode_responses=True))
    params.set("async_client", fake.aioredis.FakeRedis(server=server, decode_responses=True))
    for key, value in overrides.items():
        params.set(key, value)
    return RedisCacheRegion(
        domain=cast("str", params.get("domain")),
        sync_client=cast("Any", params.get("sync_client")),
        async_client=cast("Any", params.get("async_client")),
    )


def test_properties_and_lazy_shared_clients() -> None:
    """属性暴露注入客户端；未注入时经共享客户端惰性取用。"""
    sync_client = fakeredis.FakeRedis(decode_responses=True)
    async_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    region = RedisCacheRegion(
        domain="demo", sync_client=cast("Any", sync_client), async_client=cast("Any", async_client)
    )
    assert region.domain == "demo"
    assert region.sync_client is sync_client
    assert region.async_client is async_client

    shared = RedisRedisClient(
        "redis://localhost:6379/0",
        sync_client=cast("Any", fakeredis.FakeRedis(decode_responses=True)),
        async_client=cast("Any", fakeredis.aioredis.FakeRedis(decode_responses=True)),
    )
    set_shared_redis_client(shared)
    try:
        lazy = RedisCacheRegion(domain="lazy")
        assert lazy.sync_client is shared.sync_client()
        assert lazy.async_client is shared.async_client()
    finally:
        clear_shared_redis_client()


def test_ttl_with_jitter_bounds() -> None:
    """抖动 TTL：缺省取 `default_ttl`；（非正）原样返回；正值落在 [base, base+10%]。"""
    region = _region()
    assert region.ttl_with_jitter() >= region.default_ttl
    assert region.ttl_with_jitter() <= region.default_ttl + max(1, int(region.default_ttl * 0.1))
    assert region.ttl_with_jitter(0) == 0
    assert region.ttl_with_jitter(-3) == -3

    value = region.ttl_with_jitter(100)
    assert 100 <= value <= 110


async def test_sync_and_async_round_trip_and_lock() -> None:
    """同步 / 异步读写删、版本号 `INCR`、互斥锁获取与令牌释放、`clear`。"""
    region = _region()

    assert region.get("missing") is None

    region.set("k", json.loads('{"a": 1}'))
    assert region.get("k") == {"a": 1}
    assert region.delete("k") is True
    assert region.get("k") is None

    # 非正 TTL → 不设过期（另一分支）。
    region.set("k0", "v0", 0)

    await region.aset("k2", json.loads('{"b": 2}'), 60)
    assert await region.aget("k2") == {"b": 2}
    await region.aset("k2b", "v2b", 0)
    assert await region.adelete("k2") is True
    assert await region.aget("k2") is None

    version_key = region.build_key("version")
    assert await region.aincrease(version_key) == 1
    assert region.get_global_version() == 1

    assert await region.asetnx("lock", "tok", 5) is True
    assert await region.asetnx("lock", "other", 0) is False
    assert await region.arelease_lock("lock", "tok") is True

    region.set("k3", json.loads('{"c": 3}'))
    region.clear()
    assert region.get("k3") is None


def test_load_handles_raw_shapes() -> None:
    """`_load` 对 JSON 非法 / 非字符串值的处理（脏值按未命中）。"""
    region = _region()
    region.sync_client.set("plain", "not-json")
    assert region.get("plain") is None

    region.sync_client.set("bytes", b'{"x": 1}')
    assert region.get("bytes") == json.loads('{"x": 1}')

    region.sync_client.set("number", 5)
    assert region.get("number") == 5


async def test_setup_warmup_with_url_uses_shared_client() -> None:
    """`setup()` 预热：给出 `url` 且无注入客户端时经共享客户端取用（不建连）。"""
    shared = RedisRedisClient(
        "redis://localhost:6379/0",
        sync_client=cast("Any", fakeredis.FakeRedis(decode_responses=True)),
        async_client=cast("Any", fakeredis.aioredis.FakeRedis(decode_responses=True)),
    )
    set_shared_redis_client(shared)
    try:
        region = RedisCacheRegion(domain="warm", url="redis://localhost:6379/0")
        await region.setup()
        assert region.sync_client is shared.sync_client()
        assert region.async_client is shared.async_client()
    finally:
        clear_shared_redis_client()


def test_load_and_to_int_helpers() -> None:
    """`_load` / `_to_int` 原始值归一：字节解码、非字符串原样、非法 JSON / 非法整数回落。"""
    assert _load(None) is None
    assert _load(b'{"a": 1}') == {"a": 1}
    assert _load(7) == 7
    assert _load("not-json") is None

    assert _to_int(None) == 0
    assert _to_int(b"5") == 5
    assert _to_int("9") == 9
    assert _to_int("nope") == 0


async def test_degrade_paths_return_safe_defaults() -> None:
    """客户端异常：读未命中、写空操作、删 False、版本 0、锁放行 / 释放失败、`clear` 空操作。"""
    region = RedisCacheRegion(domain="demo", sync_client=cast("Any", _Broken()), async_client=cast("Any", _Broken()))

    assert region.get("k") is None
    region.set("k", "v")
    assert region.delete("k") is False
    assert region.get_global_version() == 0

    assert await region.aget("k") is None
    await region.aset("k", "v")
    assert await region.adelete("k") is False
    assert await region.aincrease("k") == 0
    assert await region.asetnx("lock", "tok", 5) is True
    assert await region.arelease_lock("lock", "tok") is False
    region.clear()


async def test_aclose_idempotent_and_degrades_on_close_failure() -> None:
    """`aclose()`：关闭失败仅降级日志；重复调用幂等。"""
    region = RedisCacheRegion(domain="demo", sync_client=cast("Any", _Broken()), async_client=cast("Any", _Broken()))
    await region.setup()
    await region.aclose()
    await region.aclose()
