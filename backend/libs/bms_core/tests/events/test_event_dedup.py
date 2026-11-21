"""消费幂等短窗口护栏：只读预判 / 成功后标记 / Redis 降级。

依据《详细设计 · 事件总线》§4.5：L1 不用处理前 SETNX——处理前占位会让「处理失败回滚」后的重投
被跳过，把至少一次退化成至多一次（事件永久丢失）。本用例锁住这个语义。
"""

from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.events.dedup import EventConsumeDedup, dedup_key

pytestmark = pytest.mark.kiwi_id(2370)


class _BrokenClient:
    """恒抛连接异常的客户端替身（验证降级放行）。"""

    async def exists(self, *args: object, **kwargs: object) -> int:
        """恒定抛错。"""
        raise ConnectionError("redis down")

    async def set(self, *args: object, **kwargs: object) -> None:
        """恒定抛错。"""
        raise ConnectionError("redis down")


class _UnavailableClient:
    """恒抛 `RedisUnavailableError` 的客户端替身（验证不可用分支）。"""

    async def mget(self, *args: object, **kwargs: object) -> object:
        """恒定抛错。"""
        raise RedisUnavailableError("redis unavailable")

    def pipeline(self, *args: object, **kwargs: object) -> object:
        """恒定抛错。"""
        raise RedisUnavailableError("redis unavailable")


def _client() -> Redis:
    """构造 fakeredis 异步客户端。

    Returns:
        Redis: 假客户端。
    """
    return cast("Redis", FakeRedis())


def test_dedup_key_layout() -> None:
    """键口径符合 `bms:{租户|global}:{域}:{业务键}`。"""
    assert dedup_key(group="bms.audit.chain", event_id="evt-1") == "bms:global:event:consumed:bms.audit.chain:evt-1"


async def test_seen_is_false_before_remember() -> None:
    """未标记时预判为 False（首次处理照常进入业务事务）。"""
    dedup = EventConsumeDedup(client=_client())
    assert await dedup.seen(group="g.one", event_id="evt-1") is False


async def test_remember_marks_seen() -> None:
    """标记后预判为 True（窗口内重复投递直接跳过）。"""
    dedup = EventConsumeDedup(client=_client())
    await dedup.remember(group="g.one", event_id="evt-1")
    assert await dedup.seen(group="g.one", event_id="evt-1") is True


async def test_seen_is_scoped_by_group() -> None:
    """不同消费组互不影响（同事件被多个组各消费一次）。"""
    dedup = EventConsumeDedup(client=_client())
    await dedup.remember(group="g.one", event_id="evt-1")
    assert await dedup.seen(group="g.two", event_id="evt-1") is False


async def test_remember_sets_ttl() -> None:
    """标记带 TTL（短窗口，不无限增长）。"""
    client = _client()
    dedup = EventConsumeDedup(ttl=30, client=client)
    await dedup.remember(group="g.one", event_id="evt-1")
    ttl = await client.ttl(dedup_key(group="g.one", event_id="evt-1"))
    assert 0 < ttl <= 30


async def test_seen_degrades_when_redis_down() -> None:
    """Redis 不可用时预判放行（False），由 L2 唯一约束兜底——不得 fail-closed 停掉事件流。"""
    dedup = EventConsumeDedup(client=cast("Redis", _BrokenClient()))
    assert await dedup.seen(group="g.one", event_id="evt-1") is False


async def test_remember_is_noop_when_redis_down() -> None:
    """Redis 不可用时标记静默跳过（只影响效率，不影响正确性）。"""
    dedup = EventConsumeDedup(client=cast("Redis", _BrokenClient()))
    await dedup.remember(group="g.one", event_id="evt-1")


async def test_remember_is_idempotent() -> None:
    """重复标记无副作用（重试成功后重复写同一键）。"""
    dedup = EventConsumeDedup(client=_client())
    await dedup.remember(group="g.one", event_id="evt-1")
    await dedup.remember(group="g.one", event_id="evt-1")
    assert await dedup.seen(group="g.one", event_id="evt-1") is True


async def test_seen_many_and_remember_many() -> None:
    """批量判读 / 批量标记与逐条语义一致（一次 MGET + 一次 pipeline）。"""
    dedup = EventConsumeDedup(client=_client())
    await dedup.remember_many(group="g.one", event_ids=ConcurrentStableList(["evt-1", "evt-2"]))
    outcome = await dedup.seen_many(group="g.one", event_ids=ConcurrentStableList(["evt-1", "evt-3"]))
    assert outcome["evt-1"] is True
    assert outcome["evt-3"] is False


async def test_batch_dedup_empty_and_degraded() -> None:
    """空列表直接返回；Redis 不可用时批量判读放行、批量标记静默跳过。"""
    dedup = EventConsumeDedup(client=_client())
    assert dict((await dedup.seen_many(group="g.one", event_ids=ConcurrentStableList())).items()) == {}
    await dedup.remember_many(group="g.one", event_ids=ConcurrentStableList())

    broken = EventConsumeDedup(client=cast("Redis", _BrokenClient()))
    degraded = await broken.seen_many(group="g.one", event_ids=ConcurrentStableList(["evt-1"]))
    assert degraded["evt-1"] is False
    await broken.remember_many(group="g.one", event_ids=ConcurrentStableList(["evt-1"]))


async def test_batch_dedup_unavailable_branch() -> None:
    """`RedisUnavailableError` 分支：批量判读放行、批量标记直接返回。"""
    unavailable = EventConsumeDedup(client=cast("Redis", _UnavailableClient()))
    outcome = await unavailable.seen_many(group="g.one", event_ids=ConcurrentStableList(["evt-1"]))
    assert outcome["evt-1"] is False
    await unavailable.remember_many(group="g.one", event_ids=ConcurrentStableList(["evt-1"]))


@pytest.mark.parametrize("group", ["g.one", "bms.audit.chain"])
async def test_multiple_events_independent(group: str) -> None:
    """同组内不同事件各自独立去重。"""
    dedup = EventConsumeDedup(client=_client())
    await dedup.remember(group=group, event_id="evt-1")
    assert await dedup.seen(group=group, event_id="evt-1") is True
    assert await dedup.seen(group=group, event_id="evt-2") is False
