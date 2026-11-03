"""国际化缓存跨实例一致性（真 Redis，Kiwi 2404）：A 写 + 失效 → B 下一次读回源。

未配置 `BMS_REDIS__URL` 时自动跳过（不计覆盖率分母）。断言口径：

1. 共享层键被删后 B 仍命中自己 L1（证明 L1 生效、不回源）；
2. A 失效（版本递增）后 B 用新版本读取拿到新值，旧版本载荷不再命中（证明版本比对跨实例生效）。
"""

import os

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.i18n.cache import RedisI18nCacheRegion
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.registry_null import NullLocaleRegistry

pytestmark = pytest.mark.kiwi_id(2404)

_REDIS_URL = os.environ.get("BMS_REDIS__URL", "")
_TENANT = "1001"
_LOCALE = "zh-CN"


def _messages(value: str) -> ConcurrentStableDict[str, str]:
    """构造单条文案。

    Args:
        value: 文案值。

    Returns:
        ConcurrentStableDict[str, str]: 文案映射。
    """
    return ConcurrentStableDict({"common.confirm": value})


@pytest.mark.skipif(not _REDIS_URL, reason="未配置 BMS_REDIS__URL（真 Redis 集成用例）")
async def test_cross_instance_invalidate_visible() -> None:
    """A 失效后 B 读到新值；失效前 B 命中 L1。"""
    region_a = RedisI18nCacheRegion(url=_REDIS_URL)
    region_b = RedisI18nCacheRegion(url=_REDIS_URL)
    key = region_a.messages_cache_key(_TENANT, _LOCALE)
    try:
        await region_a.aset_messages(_TENANT, _LOCALE, _messages("旧值"), version=0, ttl=300)
        assert await region_b.aget_messages(_TENANT, _LOCALE, version=0) == _messages("旧值")

        # 共享层键被删后 B 仍命中 L1（证明 L1 生效）
        await region_a.redis_region.adelete(key)
        assert await region_b.aget_messages(_TENANT, _LOCALE, version=0) == _messages("旧值")

        invalidator = I18nInvalidator(region_a, NullLocaleRegistry())
        latest = await invalidator.invalidate_messages(ConcurrentStableList((_LOCALE,)))
        assert latest >= 1
        await region_a.aset_messages(_TENANT, _LOCALE, _messages("新值"), version=latest, ttl=300)

        assert await region_b.aget_messages(_TENANT, _LOCALE, version=latest) == _messages("新值")
        assert await region_b.aget_messages(_TENANT, _LOCALE, version=0) is None
    finally:
        await region_a.redis_region.adelete(key)
        await region_a.aclose()
        await region_b.aclose()
