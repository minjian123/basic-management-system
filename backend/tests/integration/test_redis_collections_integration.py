"""真实 Redis 集成用例（标记 integration；需 BMS_TEST_REDIS_URL，随 04_02 执行）。"""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.redis_collections import RedisSortedDict, RedisSortedSet

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    """真实 Redis 客户端（未配置 BMS_TEST_REDIS_URL 时跳过）。"""
    url = os.environ.get("BMS_TEST_REDIS_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_REDIS_URL，跳过真实 Redis 集成用例")
    client: Redis = Redis.from_url(url, decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def key_prefix() -> str:
    """隔离 key 前缀（用例结束清理）。"""
    return f"bms:global:collections:itest:{uuid4().hex}"


async def test_real_redis_sorted_dict_compound_ops(redis_client: Redis, key_prefix: str) -> None:
    """真实 Redis：Lua 原子、WATCH 乐观更新与上下文提交。"""
    mapping = RedisSortedDict[str, str](redis_client, key_prefix)
    await mapping.set("b", "2")
    await mapping.set("a", "1")
    assert await mapping.items() == [("a", "1"), ("b", "2")]
    assert await mapping.replace_if_equal("a", "1", "9") is True
    assert await mapping.replace_if_equal("a", "1", "8") is False
    assert await mapping.get_and_remove("b") == "2"
    assert await mapping.update_atomic("a", lambda value: value + "!") == "9!"
    async with mapping.get_locked("a") as holder:
        holder.value = holder.value + "?"
    assert await mapping.get("a") == "9!?"
    assert await mapping.version() >= 1
    await redis_client.delete(f"{key_prefix}:index", f"{key_prefix}:data", f"{key_prefix}:version")


async def test_real_redis_sorted_set_ops(redis_client: Redis, key_prefix: str) -> None:
    """真实 Redis：ZSET 有序查询与版本号。"""
    zset = RedisSortedSet[str](redis_client, f"{key_prefix}:zset")
    await zset.add("a", 1.0)
    await zset.add("b", 2.0)
    assert await zset.top(1) == ["b"]
    assert await zset.range_by_rank() == ["a", "b"]
    assert await zset.version() >= 1
    await redis_client.delete(f"{key_prefix}:zset", f"{key_prefix}:zset:version")
