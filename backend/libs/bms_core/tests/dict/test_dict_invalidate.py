"""字典版本化失效（Kiwi 2372）：删各语言类型键与 id 子集键 + 递增版本号。

对应详细设计 §4.3：失效＝DEL（省重算）+ INCR（跨实例信号）；Redis 抖动失败只告警不阻断；
`[dict].invalidate_on_write=false` 时退化为 no-op。
"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.invalidate import DictInvalidator
from bms_core.i18n.base import SUPPORTED_LOCALES


class _BrokenCache(MemoryDictCacheRegion):
    """失效即抛错的缓存域（模拟 Redis 抖动）。"""

    async def adrop_type(self, tenant: str | None, locale: str, data_source_key: str) -> None:
        """恒抛错。

        Args:
            tenant: 租户标识。
            locale: 语言。
            data_source_key: 字典类型码。

        Raises:
            RuntimeError: 恒抛。
        """
        raise RuntimeError("redis down")


@pytest.mark.kiwi_id(2372)
async def test_invalidate_drops_type_and_subset_keys() -> None:
    """失效后各语言的类型键与 id 子集键都被删除，版本号 +1。"""
    cache = MemoryDictCacheRegion()
    for locale in SUPPORTED_LOCALES:
        await cache.aset_type("demo", locale, "role", {"version": 0, "items": [], "has_more": False, "total": 0}, 60)
        await cache.aset_id_subset("demo", locale, "role", ConcurrentStableDict({1: "管理员"}))
    invalidator = DictInvalidator(cache)
    version = await invalidator.invalidate(ConcurrentStableList(("role",)), tenant="demo")
    assert version == 1
    for locale in SUPPORTED_LOCALES:
        assert await cache.aget_type("demo", locale, "role") is None
        assert dict((await cache.aid_subset("demo", locale, "role", ConcurrentStableList((1,)))).items()) == {}


@pytest.mark.kiwi_id(2372)
async def test_invalidate_only_touches_given_keys() -> None:
    """只失效传入的 key（同租户其他字典的缓存保持）。"""
    cache = MemoryDictCacheRegion()
    await cache.aset_type("demo", "zh-CN", "role", {"version": 0}, 60)
    await cache.aset_type("demo", "zh-CN", "user", {"version": 0}, 60)
    invalidator = DictInvalidator(cache)
    await invalidator.invalidate(ConcurrentStableList(("role",)), tenant="demo")
    assert await cache.aget_type("demo", "zh-CN", "role") is None
    assert await cache.aget_type("demo", "zh-CN", "user") is not None


@pytest.mark.kiwi_id(2372)
async def test_disabled_or_empty_is_noop() -> None:
    """未启用或空 key 列表：版本号不变、缓存不动。"""
    cache = MemoryDictCacheRegion()
    await cache.aset_type("demo", "zh-CN", "role", {"version": 0}, 60)
    disabled = DictInvalidator(cache, enabled=False)
    assert await disabled.invalidate(ConcurrentStableList(("role",)), tenant="demo") == 0
    assert await cache.aget_type("demo", "zh-CN", "role") is not None
    enabled = DictInvalidator(cache)
    assert await enabled.invalidate(ConcurrentStableList(()), tenant="demo") == 0


@pytest.mark.kiwi_id(2372)
async def test_cache_failure_does_not_raise() -> None:
    """失效失败只告警：返回 0、异常不外抛（不反噬业务写）。"""
    invalidator = DictInvalidator(_BrokenCache())
    assert await invalidator.invalidate(ConcurrentStableList(("role",)), tenant="demo") == 0


@pytest.mark.kiwi_id(2372)
async def test_enabled_property_reflects_option() -> None:
    """`enabled` 反映装配开关（供调用方与用例核对）。"""
    assert DictInvalidator(MemoryDictCacheRegion()).enabled is True
    assert DictInvalidator(MemoryDictCacheRegion(), enabled=False).enabled is False
