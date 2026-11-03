"""国际化缓存域测试（Kiwi 2404）：版本化载荷 / 清单与语言包读写 / L1 + Redis 两层。"""

import pytest
from fakeredis import (
    FakeRedis,
    FakeServer,  # pyright: ignore[reportAttributeAccessIssue, reportUnknownVariableType]
)
from fakeredis.aioredis import FakeRedis as FakeAsyncRedis

from bms_core.cache.redis import RedisCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.i18n.cache import (
    MemoryI18nCacheRegion,
    RedisI18nCacheRegion,
    build_locales_payload,
    build_messages_payload,
    read_locales_payload,
    read_messages_payload,
)
from bms_core.i18n.locale import LocaleInfo

pytestmark = [pytest.mark.kiwi_id(2404)]

_TENANT = "1001"


def _messages() -> ConcurrentStableDict[str, str]:
    """构造文案映射。

    Returns:
        ConcurrentStableDict[str, str]: key → 文案。
    """
    return ConcurrentStableDict({"common.confirm": "确认", "common.cancel": "取消"})


def _locales() -> ConcurrentStableList[LocaleInfo]:
    """构造语言清单。

    Returns:
        ConcurrentStableList[LocaleInfo]: 清单条目。
    """
    return ConcurrentStableList(
        (LocaleInfo(code="zh-CN", name="简体中文", is_default=True, sort=0), LocaleInfo(code="en-US", sort=10))
    )


def test_payload_roundtrip_and_dirty() -> None:
    """载荷往返；版本不符 / 结构非法按未命中。"""
    payload = build_messages_payload(3, _messages())
    assert read_messages_payload(payload, 3) == _messages()
    assert read_messages_payload(payload, 4) is None
    assert read_messages_payload("x", 3) is None
    assert read_messages_payload({"v": 3}, 3) is None
    assert read_messages_payload({"v": 3, "messages": "bad"}, 3) is None

    locales = build_locales_payload(1, _locales())
    assert read_locales_payload(locales, 1) == _locales()
    assert read_locales_payload(locales, 2) is None
    assert read_locales_payload("x", 1) is None
    assert read_locales_payload({"v": 1, "locales": "bad"}, 1) is None
    assert read_locales_payload({"v": 1, "locales": [{"name": "x"}]}, 1) is None
    assert read_locales_payload({"v": 1, "locales": [{"code": "zh-CN", "sort": "3"}]}, 1) == ConcurrentStableList(
        (LocaleInfo(code="zh-CN", sort=3),)
    )


async def test_memory_region_messages_and_locales() -> None:
    """进程内实现：版本化读写 / 删除 / 版本递增。"""
    region = MemoryI18nCacheRegion()
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) is None
    await region.aset_messages(_TENANT, "zh-CN", _messages(), version=0, ttl=60)
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) == _messages()
    assert await region.aget_messages(_TENANT, "zh-CN", version=1) is None
    await region.adrop_messages(_TENANT, "zh-CN")
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) is None

    assert await region.aget_locales(_TENANT, version=0) is None
    await region.aset_locales(_TENANT, _locales(), version=0, ttl=60)
    assert await region.aget_locales(_TENANT, version=0) == _locales()
    await region.adrop_locales(_TENANT)
    assert await region.aget_locales(_TENANT, version=0) is None

    assert await region.aversion(_TENANT) == 0
    assert await region.aincrease_version(_TENANT) == 1
    assert await region.aversion(_TENANT) == 1
    assert region.get_global_version() == 1


async def test_memory_region_sync_contract_proxy() -> None:
    """同步契约代理：get / set / delete 与 L1 一致。"""
    region = MemoryI18nCacheRegion()
    region.set("k", {"a": 1}, 60)
    assert region.get("k") == {"a": 1}
    assert region.delete("k") is True
    assert region.delete("k") is False
    assert region.get("k") is None


def _redis_region() -> RedisI18nCacheRegion:
    """构造基于 fakeredis 的 Redis 缓存域（同步 + 异步共用一份内存数据）。

    Returns:
        RedisI18nCacheRegion: Redis 缓存域实例。
    """
    server = FakeServer()
    return RedisI18nCacheRegion(
        redis_region=RedisCacheRegion(
            domain="i18n",
            sync_client=FakeRedis(server=server),  # pyright: ignore[reportCallIssue, reportArgumentType]
            async_client=FakeAsyncRedis(server=server),  # pyright: ignore[reportCallIssue, reportArgumentType]
        )
    )


async def test_redis_region_messages_and_locales() -> None:
    """Redis 实现：L1 + 共享层版本化读写 / 删除 / 版本递增。"""
    region = _redis_region()
    await region.setup()
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) is None
    await region.aset_messages(_TENANT, "zh-CN", _messages(), version=0, ttl=60)
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) == _messages()
    # 版本变化后视为未命中（L1 与共享层都带版本）
    assert await region.aget_messages(_TENANT, "zh-CN", version=5) is None
    await region.adrop_messages(_TENANT, "zh-CN")
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) is None

    await region.aset_locales(_TENANT, _locales(), version=0, ttl=60)
    assert await region.aget_locales(_TENANT, version=0) == _locales()
    await region.adrop_locales(_TENANT)
    assert await region.aget_locales(_TENANT, version=0) is None

    assert await region.aversion(_TENANT) == 0
    assert await region.aincrease_version(_TENANT) == 1
    assert await region.aversion(_TENANT) == 1
    assert region.get_global_version() >= 0
    await region.aclose()


async def test_redis_region_l1_hit_avoids_shared_layer() -> None:
    """命中 L1 后不再访问共享层（第二次读不看 Redis）。"""
    region = _redis_region()
    await region.aset_messages(_TENANT, "zh-CN", _messages(), version=0, ttl=60)
    first = await region.aget_messages(_TENANT, "zh-CN", version=0)
    assert first == _messages()
    # 直接从 L1 读：共享层键被删也能命中（证明 L1 生效）
    await region.redis_region.adelete(region.messages_cache_key(_TENANT, "zh-CN"))
    assert await region.aget_messages(_TENANT, "zh-CN", version=0) == _messages()


async def test_redis_region_sync_contract_and_dirty_version() -> None:
    """同步契约代理与版本键脏值（非数字按 0）。"""
    region = _redis_region()
    region.set("k", {"a": 1}, 60)
    assert region.get("k") == {"a": 1}
    assert region.delete("k") is True
    assert region.delete("k") is False
    await region.redis_region.aset(region.version_cache_key(_TENANT), "oops", 0)
    assert await region.aversion(_TENANT) == 0


async def test_redis_region_shared_layer_hit_backfills_l1() -> None:
    """共享层命中回填 L1：只写 Redis 后读一次（L1 为空）再读一次（命中 L1）。"""
    region = _redis_region()
    version = await region.aversion(_TENANT)
    await region.redis_region.aset(
        region.messages_cache_key(_TENANT, "zh-CN"), build_messages_payload(version, _messages()), 60
    )
    assert await region.aget_messages(_TENANT, "zh-CN", version=version) == _messages()

    await region.redis_region.aset(region.locales_cache_key(_TENANT), build_locales_payload(version, _locales()), 60)
    assert await region.aget_locales(_TENANT, version=version) == _locales()


async def test_redis_region_sync_get_from_shared_layer() -> None:
    """同步 `get` 在 L1 未命中时回源共享层并回填。"""
    region = _redis_region()
    await region.redis_region.aset("probe", {"a": 2}, 60)
    assert region.get("probe") == {"a": 2}
    assert region.get("absent") is None
    assert await region.adrop_messages(_TENANT, "fr-FR") is None


def test_locales_payload_rejects_non_mapping_row() -> None:
    """清单载荷元素非映射按未命中。"""
    assert read_locales_payload({"v": 0, "locales": ["bad"]}, 0) is None
