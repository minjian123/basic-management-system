"""国际化版本化失效：写路径提交后作废语言包 / 语言清单缓存并递增版本。

口径（概要 29 §3.1 / §4）：

- **顺序**：先提交业务事务、再调本失效器；失败只告警、不反噬业务写——正确性由版本比对 + TTL 兜底。
- **语言清单变更连带失效全部语言包**：切换默认语言会改变**所有语言**的回退结果，rtl / 启停同样影响
  前端渲染口径；故清单写路径必须「清单键 + 全部语言包键」一起失效。
- **先删后增**：`INCR` 放在删除之后，避免并发读把旧值以新版本号写回成「污染的有效载荷」。
- **快照同步**：失效后调一次 `registry.refresh()`，让本实例的同步解析立刻看到新清单。
"""

from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_id_str
from bms_core.i18n.cache import I18nCacheRegion
from bms_core.i18n.registry import BaseLocaleRegistry

__all__ = ["I18nInvalidator", "get_i18n_invalidator"]

_LOGGER = get_logger("bms")


class I18nInvalidator(BaseFrameworkObject):
    """国际化缓存失效器（写路径的单一入口）。"""

    def __init__(self, cache: I18nCacheRegion, registry: BaseLocaleRegistry) -> None:
        """初始化。

        Args:
            cache: 国际化缓存域（与应用取数共用同一实例）。
            registry: 语言清单能力域（失效后刷新进程内快照）。
        """
        self._cache = cache
        self._registry = registry

    async def invalidate_messages(self, locales: ConcurrentStableList[str], *, tenant: str | None = None) -> int:
        """作废指定语言包并递增版本（语言包保存路径）。

        Args:
            locales: 受影响语言（插入序）。
            tenant: 租户标识；None 取当前租户上下文。

        Returns:
            int: 递增后的版本号；失效失败返回 0（调用方不以此为业务判据）。
        """
        resolved = tenant if tenant is not None else current_tenant_id_str()
        try:
            for locale in locales:
                await self._cache.adrop_messages(resolved, locale)
            version = await self._cache.aincrease_version(resolved)
        except Exception as exc:  # 失效失败不得反噬业务写；版本比对与 TTL 兜底
            _LOGGER.warning("i18n_invalidate_failed", scope="messages", error_type=type(exc).__name__)
            return 0
        _LOGGER.info("i18n_messages_invalidated", locales=list(locales), version=version)
        return version

    async def invalidate_all(self, *, tenant: str | None = None) -> int:
        """作废语言清单与全部语言包并递增版本（清单写路径 / 显式失效端点）。

        Args:
            tenant: 租户标识；None 取当前租户上下文。

        Returns:
            int: 递增后的版本号；失效失败返回 0。
        """
        resolved = tenant if tenant is not None else current_tenant_id_str()
        locales: ConcurrentStableList[str] = ConcurrentStableList()
        try:
            await self._registry.refresh()
            locales = ConcurrentStableList(item.code for item in self._registry.snapshot())
            for locale in locales:
                await self._cache.adrop_messages(resolved, locale)
            await self._cache.adrop_locales(resolved)
            version = await self._cache.aincrease_version(resolved)
        except Exception as exc:
            _LOGGER.warning("i18n_invalidate_failed", scope="all", error_type=type(exc).__name__)
            return 0
        _LOGGER.info("i18n_all_invalidated", locales=len(locales), version=version)
        return version


def get_i18n_invalidator(request: Request) -> I18nInvalidator:
    """取应用级失效器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        I18nInvalidator: 与取数共用同一缓存域与清单能力域的失效器。
    """
    cache = cast("I18nCacheRegion", request.app.state.i18n_cache_region)
    registry = cast("BaseLocaleRegistry", request.app.state.locale_registry)
    return I18nInvalidator(cache, registry)
