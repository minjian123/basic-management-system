"""i18n 装配边界：Redis 缓存域工厂与字典失效器的语言回落。

补齐模块级覆盖率门禁的装配期分支（推送环按「行 + 分支」双 100% 判）：
- `RedisI18nCacheRegionFactory.create()`：取 `[i18n].l1_max_items` 与 `[redis].url` 构造缓存域；
- `DictInvalidator.locales`：清单能力域已登记但快照为空 → 回落出厂语言常量。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.core.assembly import RedisI18nCacheRegionFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.invalidate import DictInvalidator
from bms_core.i18n.base import SUPPORTED_LOCALES
from bms_core.i18n.cache import RedisI18nCacheRegion

pytestmark = [pytest.mark.kiwi_id(2404)]


def _empty_snapshot_registry() -> SimpleNamespace:
    """清单能力域替身：已登记但快照为空（如装配完成、尚未预热）。

    **刻意不继承 `BaseLocaleRegistry`**：任何 `BasePluggable` 子类都会被 `__init_subclass__`
    自动登记，测试替身继承后会与 `(locale_registry, null)` 重名，导致全量跑时注册表构建失败。

    Returns:
        SimpleNamespace: 仅提供 `snapshot()` 的替身。
    """
    return SimpleNamespace(snapshot=lambda: ConcurrentStableList())


def test_redis_cache_region_factory_creates_region() -> None:
    """Redis 缓存域工厂按配置构造实例（不建连接，构造期即可判定）。"""
    factory = RedisI18nCacheRegionFactory(get_settings())
    region = factory.create()
    assert isinstance(region, RedisI18nCacheRegion)


def test_dict_invalidator_locales_falls_back_when_snapshot_empty() -> None:
    """清单快照为空 → 失效语言回退出厂常量（不漏失效）。"""
    invalidator = DictInvalidator(MemoryDictCacheRegion(), registry=cast("Any", _empty_snapshot_registry()))
    assert invalidator.locales == ConcurrentStableList(SUPPORTED_LOCALES)
