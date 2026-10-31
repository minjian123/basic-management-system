"""参数缓存版本化用例（Kiwi 2373）：载荷版本比对 / 缺失负缓存 / 旧载荷兼容 / 双实例一致性。

覆盖：
- 内存域：版本不一致即丢弃（写方 `INCR` 后旧 L1 立即失效）、缺失标记优先于值、版本 0 表示不比对；
- Redis 域：载荷 JSON 可往返、跨实例（各持 L1、共享 Redis）失效后下一次读回源、共享旧载荷被清；
- 旧格式载荷（纯字符串）按未命中处理；空实现的负缓存写入为空操作。
"""

import json

import pytest

from bms_core.cache.redis import RedisCacheRegion
from bms_core.config.base import ConfigCacheEntry, ConfigCacheRegion
from bms_core.config.cache import MemoryConfigCacheRegion, RedisConfigCacheRegion
from bms_core.config.null import NullConfigCacheRegion

pytestmark = pytest.mark.kiwi_id(2373)


async def test_memory_region_discards_stale_version() -> None:
    """内存域：写入版本与当前版本不一致时按未命中，并清掉本地条目。"""
    region = MemoryConfigCacheRegion()
    await region.aset_value_at("t1", "password.min_length", "8", 3)
    assert await region.aget_value_at("t1", "password.min_length", 3) == "8"
    assert await region.aget_value_at("t1", "password.min_length", 4) is None
    assert await region.aget_value_at("t1", "password.min_length", 4) is None


async def test_memory_region_version_zero_skips_check() -> None:
    """内存域：版本 0 表示不比对（`[config].version_check=false` 的排障路径）。"""
    region = MemoryConfigCacheRegion()
    await region.aset_value_at("t1", "session.max_active", "5", 7)
    assert await region.aget_value_at("t1", "session.max_active", 0) == "5"


async def test_memory_region_missing_marker() -> None:
    """内存域：缺失负缓存返回「确认不存在」载荷，取值接口返回 None。"""
    region = MemoryConfigCacheRegion()
    await region.aset_missing("t1", "not.exists", 1, 30)
    entry = await region.aget_entry("t1", "not.exists", 1)
    assert entry is not None
    assert entry.missing is True
    assert await region.aget_value_at("t1", "not.exists", 1) is None


async def test_memory_region_old_payload_is_miss() -> None:
    """旧格式载荷（纯字符串）按未命中处理，回源后由新载荷覆盖。"""
    region = MemoryConfigCacheRegion()
    region.set(region.config_key("t1", "menu.tree_cache_ttl"), "300")
    assert await region.aget_entry("t1", "menu.tree_cache_ttl", 0) is None
    await region.aset_value_at("t1", "menu.tree_cache_ttl", "60", 0)
    assert await region.aget_value_at("t1", "menu.tree_cache_ttl", 0) == "60"


def test_entry_payload_roundtrip() -> None:
    """载荷结构：内置 dict 形态的版本 / 值 / 缺失三键，可被 JSON 原样往返。"""
    entry = ConfigCacheEntry(version=2, value="true")
    payload = {"v": entry.version, "value": entry.value, "missing": entry.missing}
    restored = json.loads(json.dumps(payload))
    assert restored == {"v": 2, "value": "true", "missing": False}


async def test_null_region_missing_is_noop() -> None:
    """空实现：负缓存写入无效，读取恒未命中。"""
    region = NullConfigCacheRegion()
    await region.aset_missing(None, "k", 1, 30)
    assert await region.aget_entry(None, "k", 1) is None


class _PrimitiveRegion(ConfigCacheRegion):
    """未重写版本化接口的最小区域（验证基类缺省实现）。"""

    def __init__(self, value: object) -> None:
        self._value = value

    def get(self, key: str) -> object | None:
        """读缓存（恒定返回注入值）。

        Args:
            key: 缓存 key（忽略）。

        Returns:
            object | None: 注入值。
        """
        return self._value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（空实现）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期。
        """

    def delete(self, key: str) -> bool:
        """删缓存（恒 False）。

        Args:
            key: 缓存 key。

        Returns:
            bool: False。
        """
        return False

    def get_global_version(self) -> int:
        """取全局版本号（恒 0）。

        Returns:
            int: 0。
        """
        return 0


async def test_base_region_default_impls() -> None:
    """基类缺省实现：字符串值按当前版本成载荷，非字符串按未命中。"""
    primitive = _PrimitiveRegion("300")
    entry = await primitive.aget_entry(None, "menu.tree_cache_ttl", 5)
    assert entry is not None
    assert entry.value == "300"
    assert await primitive.aget_value_at(None, "menu.tree_cache_ttl", 5) == "300"

    empty = _PrimitiveRegion(None)
    assert await empty.aget_entry(None, "menu.tree_cache_ttl", 5) is None


async def test_payload_rejects_bad_shapes() -> None:
    """载荷解析：非 dict / 版本非整数 / 值非字符串一律按未命中。"""
    region = MemoryConfigCacheRegion()
    key = region.config_key("t1", "captcha.scene.login.ttl")
    region.set(key, "300")
    assert await region.aget_entry("t1", "captcha.scene.login.ttl", 0) is None
    region.set(key, {"v": "x", "value": "300", "missing": False})
    assert await region.aget_entry("t1", "captcha.scene.login.ttl", 0) is None
    region.set(key, {"v": 1, "value": 300, "missing": False})
    assert await region.aget_entry("t1", "captcha.scene.login.ttl", 0) is None


def _redis_regions() -> tuple[RedisConfigCacheRegion, RedisConfigCacheRegion]:
    """构造共享同一 fakeredis 的两套缓存域（各持 L1，模拟两个实例）。

    Returns:
        tuple[RedisConfigCacheRegion, RedisConfigCacheRegion]: 两个实例。
    """
    fakeredis = pytest.importorskip("fakeredis")
    region = RedisConfigCacheRegion(
        redis_region=RedisCacheRegion(
            domain="config",
            sync_client=fakeredis.FakeRedis(decode_responses=True),
            async_client=fakeredis.aioredis.FakeRedis(decode_responses=True),
        )
    )
    return region, region


async def test_redis_region_cross_instance_invalidation() -> None:
    """Redis 域：A 实例失效后 B 实例下一次读按未命中（跨实例即时生效）。"""
    fakeredis = pytest.importorskip("fakeredis")
    shared_sync = fakeredis.FakeRedis(decode_responses=True)
    shared_async = fakeredis.aioredis.FakeRedis(decode_responses=True)
    first = RedisConfigCacheRegion(
        redis_region=RedisCacheRegion(domain="config", sync_client=shared_sync, async_client=shared_async)
    )
    second = RedisConfigCacheRegion(
        redis_region=RedisCacheRegion(domain="config", sync_client=shared_sync, async_client=shared_async)
    )
    version = await first.aincrease_version("t1")
    await first.aset_value_at("t1", "password.max_age_days", "90", version)
    assert await second.aget_value_at("t1", "password.max_age_days", version) == "90"

    await first.adrop_value("t1", "password.max_age_days")
    bumped = await first.aincrease_version("t1")
    assert bumped == version + 1
    assert await second.aget_value_at("t1", "password.max_age_days", bumped) is None


async def test_redis_region_stale_shared_payload_dropped() -> None:
    """Redis 域：共享层旧载荷（版本过期）被清并返回未命中。"""
    fakeredis = pytest.importorskip("fakeredis")
    shared_sync = fakeredis.FakeRedis(decode_responses=True)
    shared_async = fakeredis.aioredis.FakeRedis(decode_responses=True)
    region = RedisConfigCacheRegion(
        redis_region=RedisCacheRegion(domain="config", sync_client=shared_sync, async_client=shared_async)
    )
    await region.aset_value_at("t1", "role.code_pattern", "^[a-z]+$", 1)
    assert await region.aget_entry("t1", "role.code_pattern", 2) is None
    assert await shared_async.get(region.config_key("t1", "role.code_pattern")) is None


async def test_redis_region_negative_cache() -> None:
    """Redis 域：缺失负缓存写入共享层并在版本一致时命中。"""
    region, _ = _redis_regions()
    await region.aset_missing("t1", "custom.absent", 2, 30)
    entry = await region.aget_entry("t1", "custom.absent", 2)
    assert entry is not None
    assert entry.missing is True
    assert await region.aget_value_at("t1", "custom.absent", 2) is None
