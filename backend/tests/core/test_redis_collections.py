"""Redis 有序封装测试（Kiwi 17）。"""

from collections.abc import AsyncIterator

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.redis_collections import RedisSnapshot, RedisSortedDict, RedisSortedSet

KEY = "bms:global:collections:test"


@pytest.fixture
async def redis_client() -> AsyncIterator[FakeRedis]:
    """fakeredis 异步客户端（Lua 由 lupa 支持）。"""
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.kiwi_id(17)
async def test_redis_sorted_set_ops(redis_client: FakeRedis) -> None:
    """ZSET 有序集合：添加/累加/分值/区间/排名/删除与版本号。"""
    zset = RedisSortedSet[str](redis_client, f"{KEY}:zset")
    assert await zset.version() == 0
    assert await zset.add("a", 1.0) is True
    assert await zset.add("a", 5.0) is False
    assert await zset.incr("b", 2.0) == 2.0
    assert await zset.score("a") == 5.0
    assert await zset.score("zzz") is None
    assert await zset.range_by_rank() == ["b", "a"]
    assert await zset.top(1) == ["a"]
    assert await zset.range_by_score(0, 2) == ["b"]
    assert await zset.size() == 2
    assert await zset.remove("a") is True
    assert await zset.remove("a") is False
    assert await zset.version() == 5


@pytest.mark.kiwi_id(17)
async def test_redis_sorted_dict_ops(redis_client: FakeRedis) -> None:
    """有序字典：Lua 原子写/查/删除、键序输出与版本号。"""
    mapping = RedisSortedDict[int, str](redis_client, f"{KEY}:dict")
    assert await mapping.version() == 0
    assert mapping.version_key == f"{KEY}:dict:version"
    await mapping.set(10, "ten")
    await mapping.set(2, "two")
    await mapping.set(1, "one")
    assert await mapping.get(2) == "two"
    assert await mapping.get(999) is None
    assert await mapping.contains(1) is True
    assert await mapping.contains(999) is False
    assert await mapping.size() == 3
    assert await mapping.items() == [(1, "one"), (2, "two"), (10, "ten")]
    assert await mapping.set_if_absent(1, "九") == "one"
    assert await mapping.set_if_absent(3, "three") is None
    assert await mapping.get(3) == "three"
    assert await mapping.delete(2) is True
    assert await mapping.delete(2) is False
    assert await mapping.items() == [(1, "one"), (3, "three"), (10, "ten")]
    assert await mapping.version() == 5


@pytest.mark.kiwi_id(17)
async def test_redis_sorted_dict_string_keys(redis_client: FakeRedis) -> None:
    """字符串键按序列化字典序稳定输出。"""
    mapping = RedisSortedDict[str, str](redis_client, f"{KEY}:str")
    await mapping.set("c", "3")
    await mapping.set("a", "1")
    await mapping.set("b", "2")
    assert await mapping.items() == [("a", "1"), ("b", "2"), ("c", "3")]
    assert await mapping.items() == [("a", "1"), ("b", "2"), ("c", "3")]

    empty = RedisSortedDict[str, str](redis_client, f"{KEY}:empty")
    assert await empty.items() == []


@pytest.mark.kiwi_id(17)
async def test_redis_snapshot_lazy_reload(redis_client: FakeRedis) -> None:
    """快照：版本号变化时重载，本地失效后强制重载。"""
    zset = RedisSortedSet[str](redis_client, f"{KEY}:snap")
    loader_calls = 0

    async def loader() -> list[str]:
        nonlocal loader_calls
        loader_calls += 1
        return await zset.top(10)

    snapshot = RedisSnapshot(redis_client, zset.version_key, loader)
    assert await snapshot.get() == []
    assert loader_calls == 1
    assert await snapshot.get() == []
    assert loader_calls == 1

    await zset.add("a", 1.0)
    assert await snapshot.get() == ["a"]
    assert loader_calls == 2

    other = RedisSortedSet[str](redis_client, f"{KEY}:snap")
    await other.add("b", 2.0)
    assert await snapshot.get() == ["b", "a"]
    assert loader_calls == 3

    await snapshot.invalidate()
    assert await snapshot.get() == ["b", "a"]
    assert loader_calls == 4
