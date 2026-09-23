"""Redis 业务幂等用例（Kiwi 2173）：SETNX 前置去重 / 首次结果复用 / TTL / 不可用降级。

测试用 `fakeredis`（异步客户端，与真实 redis-py 同接口）。
"""

from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from bms_core.idempotency.base import IdempotencyStore, build_idempotency_key
from bms_core.idempotency.redis import RedisIdempotencyStore

_REDIS_URL = "redis://localhost:6379/0"


class _BrokenClient:
    """恒抛连接异常的客户端替身（验证降级）。"""

    async def set(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")

    async def get(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")


class _RawClient:
    """返回固定原始值的客户端替身（验证反序列化边界）。"""

    def __init__(self, value: object) -> None:
        """初始化。

        Args:
            value: `get` 返回的原始值。
        """
        self._value = value

    async def get(self, *args: object, **kwargs: object) -> object:
        """返回固定值。"""
        return self._value

    async def set(self, *args: object, **kwargs: object) -> bool:
        """恒定成功。"""
        return True


@pytest.mark.kiwi_id(2173)
async def test_setnx_first_and_result_reuse() -> None:
    """首次 True / 重复 False / 处理中返回 None / 保存后可复用 / TTL 生效。"""
    client = FakeRedis(decode_responses=True)
    store = RedisIdempotencyStore(_REDIS_URL, client=client)
    assert isinstance(store, IdempotencyStore)

    key = build_idempotency_key(key="pay-1", tenant="t1")
    assert await store.begin(key) is True
    assert await store.begin(key) is False
    assert await store.load(key) is None  # 处理中

    await store.save(key, {"code": 0, "data": {"id": 1}})
    assert await store.load(key) == {"code": 0, "data": {"id": 1}}
    assert await client.ttl(key) > 0

    assert await store.begin(build_idempotency_key(key="pay-2"), ttl=1) is True
    assert (await client.ttl(build_idempotency_key(key="pay-2"))) <= 1
    assert await store.load(build_idempotency_key(key="never-saved")) is None
    await client.aclose()


@pytest.mark.kiwi_id(2173)
async def test_load_deserialization_edges() -> None:
    """反序列化边界：字节 / 非字符串 / 非法 JSON / 非对象 → 按未命中。"""
    cases: list[tuple[object, object]] = [
        (None, None),
        (b'{"a": 1}', {"a": 1}),
        (123, None),
        ("{bad", None),
        ("[1, 2]", None),
        ('{"a": 1}', {"a": 1}),
    ]
    for raw, expected in cases:
        store = RedisIdempotencyStore(_REDIS_URL, client=cast("Redis", _RawClient(raw)))
        assert await store.load("bms:global:idem:k") == expected


@pytest.mark.kiwi_id(2173)
async def test_unavailable_degrades() -> None:
    """Redis 不可用：放行（唯一约束兜底）、结果不缓存，不抛错。"""
    store = RedisIdempotencyStore(_REDIS_URL, client=cast("Redis", _BrokenClient()))
    assert await store.begin("bms:global:idem:k") is True
    assert await store.load("bms:global:idem:k") is None
    await store.save("bms:global:idem:k", {"ok": True})  # 不抛错
