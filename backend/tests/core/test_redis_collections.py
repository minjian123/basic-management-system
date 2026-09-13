"""Redis 有序封装测试（Kiwi 17/18）。"""

from collections.abc import AsyncIterator, Callable

import pytest
from fakeredis.aioredis import FakeRedis
from redis.exceptions import WatchError

from app.core.base import BaseObject
from app.core.exceptions import ConcurrentConflictError
from app.core.redis_collections import RedisSnapshot, RedisSortedDict, RedisSortedSet

KEY = "bms:global:collections:test"


@pytest.mark.kiwi_id(17)
def test_inheritance_chain() -> None:
    """跨副本封装继承链：RedisSortedSet / RedisSortedDict / RedisSnapshot → BaseObject。"""
    assert issubclass(RedisSortedSet, BaseObject)
    assert issubclass(RedisSortedDict, BaseObject)
    assert issubclass(RedisSnapshot, BaseObject)


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


@pytest.mark.kiwi_id(18)
async def test_redis_replace_if_equal_and_get_and_remove(redis_client: FakeRedis) -> None:
    """CAS 与取走删除：Lua 原子语义与缺失分支。"""
    mapping = RedisSortedDict[str, str](redis_client, f"{KEY}:cas")
    await mapping.set("a", "1")
    assert await mapping.replace_if_equal("a", "1", "2") is True
    assert await mapping.get("a") == "2"
    assert await mapping.replace_if_equal("a", "1", "9") is False
    assert await mapping.replace_if_equal("zzz", "1", "9") is False
    assert await mapping.get_and_remove("a") == "2"
    assert await mapping.get_and_remove("a") is None
    assert await mapping.items() == []


@pytest.mark.kiwi_id(18)
async def test_redis_update_atomic_and_get_locked(redis_client: FakeRedis) -> None:
    """乐观更新与 WATCH 提交上下文（含缺失分支）。"""
    mapping = RedisSortedDict[str, str](redis_client, f"{KEY}:atomic")
    await mapping.set("a", "1")
    assert await mapping.update_atomic("a", lambda value: value + "!") == "1!"
    assert await mapping.get("a") == "1!"
    with pytest.raises(KeyError):
        await mapping.update_atomic("zzz", lambda value: value)

    async with mapping.get_locked("a") as holder:
        holder.value = holder.value + "?"
    assert await mapping.get("a") == "1!?"
    with pytest.raises(KeyError):
        async with mapping.get_locked("zzz"):
            pass


@pytest.mark.kiwi_id(18)
async def test_redis_update_atomic_retry_and_exhaust(redis_client: FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    """乐观重试：冲突后重放成功；超限抛 ConcurrentConflictError。"""
    mapping = RedisSortedDict[str, str](redis_client, f"{KEY}:retry")
    await mapping.set("a", "1")
    original = mapping._optimistic  # pyright: ignore[reportPrivateUsage]
    attempts = 0

    async def flaky(key: str, mutate: Callable[[str | None], str]) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise WatchError("冲突")
        return await original(key, mutate)

    monkeypatch.setattr(mapping, "_optimistic", flaky)
    assert await mapping.update_atomic("a", lambda value: value + "!") == "1!"
    assert attempts == 2

    async def always_conflict(key: str, mutate: Callable[[str | None], str]) -> str:
        raise WatchError("busy")

    monkeypatch.setattr(mapping, "_optimistic", always_conflict)
    with pytest.raises(ConcurrentConflictError):
        await mapping.update_atomic("a", lambda value: value, max_retries=2)
