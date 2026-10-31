"""字典版本化失效（02_01）：所有者域写完数据后，把「已取过的字典」整体作废。

口径（需求 01-1 §3 / 概要设计 · 字典管理 §2.3）：

- **顺序**：先提交业务事务、再调本失效器——回滚时不必失效，提交后失效才是「变更可见即作废」。
- **动作**：对每个 key × 每个支持语言删「类型键」与「id 子集键」，最后 `INCR bms:{tenant}:dict:version`。
- **正确性不依赖删除**：跨实例的一致性由**版本键**承担（各实例 L1 快照带写入时版本，读取时比对）；
  删除只是省掉一次无谓重算与内存占用。故 Redis 抖动时失效失败**只告警、不阻断业务写**。
- **范围**：只作用于字典域缓存（`DictCacheRegion`）；不触碰业务缓存与权限缓存。
"""

from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.core.plugin import resolve_plugin
from bms_core.db.tenant import current_tenant_id_str
from bms_core.dict.base import DictCacheRegion
from bms_core.i18n.base import SUPPORTED_LOCALES

__all__ = ["DictInvalidator", "get_dict_invalidator"]

_LOGGER = get_logger("bms")


class DictInvalidator(BaseFrameworkObject):
    """字典版本化失效器（所有者域写路径的单一入口）。"""

    def __init__(self, cache: DictCacheRegion, *, enabled: bool = True) -> None:
        """初始化。

        Args:
            cache: 字典缓存域（与应用取数共用同一实例；区域决定 L1 / Redis 覆盖面）。
            enabled: 是否启用（`[dict].invalidate_on_write`；关掉即退化为 no-op，便于压测 / 排障）。
        """
        self._cache = cache
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """是否启用失效。

        Returns:
            bool: 启用为 True。
        """
        return self._enabled

    async def invalidate(self, keys: ConcurrentStableList[str], *, tenant: str | None = None) -> int:
        """作废指定字典并递增版本号。

        Args:
            keys: 受影响的数据源标识（如 `("role",)`）。
            tenant: 租户标识；None 取当前租户上下文（写路径均在租户上下文内）。

        Returns:
            int: 递增后的版本号；未启用或失效失败时返回 0（调用方不以此为业务判据）。
        """
        if not self._enabled or not keys:
            return 0
        resolved = tenant if tenant is not None else current_tenant_id_str()
        try:
            for data_source_key in keys:
                for locale in SUPPORTED_LOCALES:
                    await self._cache.adrop_type(resolved, locale, data_source_key)
                    await self._cache.adrop_id_subset(resolved, locale, data_source_key)
            version = await self._cache.aincrease_version(resolved)
        except Exception as exc:  # 失效失败不得反噬业务写；正确性由 TTL 与版本比对兜底
            _LOGGER.warning("dict_invalidate_failed", keys=list(keys), error_type=type(exc).__name__)
            return 0
        _LOGGER.info("dict_invalidated", keys=list(keys), version=version)
        return version


def get_dict_invalidator(request: Request) -> DictInvalidator:
    """取应用级失效器（依赖注入提供者；开关取 `[dict].invalidate_on_write`）。

    Args:
        request: 请求对象。

    Returns:
        DictInvalidator: 与取数共用同一缓存域的失效器。
    """
    settings = cast("Settings", request.app.state.settings)
    cache = cast(
        "DictCacheRegion",
        resolve_plugin(
            "dict_cache_region",
            settings.dict_cache_region.provider,
            expected_version=DictCacheRegion.contract_version,
        ),
    )
    return DictInvalidator(cache, enabled=settings.dict_options.invalidate_on_write)
