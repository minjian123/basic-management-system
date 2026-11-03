"""i18n 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 `bms_core.i18n.base` 迁入）。

- `NullTranslator`：取词原样返回 key、语言解析取默认、语言包为空；
- `NullI18nCacheRegion`：不缓存（读恒未命中、版本恒 0），每次回源，正确性不受影响；
- `NullLocaleRegistry`：语言清单固定为种子清单（`zh-CN` 默认 / `en-US`），不读库、不读缓存。

三者的模块名以 `.null` 结尾是平台约定（迁移护栏按此判定「缺省实现落点」）。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.i18n.base import DEFAULT_LOCALE, BaseTranslator
from bms_core.i18n.cache import I18nCacheRegion
from bms_core.i18n.locale import LocaleInfo
from bms_core.i18n.registry import BaseLocaleRegistry, seed_locale_infos

__all__ = [
    "NullI18nCacheRegion",
    "NullLocaleRegistry",
    "NullTranslator",
]


class NullTranslator(BaseTranslator, BaseNullObject):
    """占位翻译器：原样返回 key（不翻译），语言解析取默认，语言包为空。"""

    async def translate(
        self, key: str, *, locale: str | None = None, params: ConcurrentStableDict[str, object] | None = None
    ) -> str:
        """原样返回 key。

        Args:
            key: 文案 key（占位原样返回）。
            locale: 语言（占位忽略）。
            params: 插值参数（占位忽略）。

        Returns:
            str: 原样 key。
        """
        return key

    async def load_messages(self, locale: str) -> ConcurrentStableDict[str, str]:
        """返回空语言包。

        Args:
            locale: 语言（占位忽略）。

        Returns:
            ConcurrentStableDict[str, str]: 空映射。
        """
        return ConcurrentStableDict()

    def resolve_locale(self, accept_language: str | None = None) -> str:
        """返回默认语言。

        Args:
            accept_language: 请求头（占位忽略）。

        Returns:
            str: `DEFAULT_LOCALE`。
        """
        return DEFAULT_LOCALE


class NullI18nCacheRegion(I18nCacheRegion, BaseNullObject):
    """占位国际化缓存：不存储任何键（读一律未命中、版本恒 0）。"""

    def get(self, key: str) -> object | None:
        """读缓存（占位恒未命中）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 恒 None。
        """
        del key
        return None

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（占位空操作）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        del key, value, ttl

    def delete(self, key: str) -> bool:
        """删缓存（占位恒未删到）。

        Args:
            key: 缓存 key。

        Returns:
            bool: 恒 False。
        """
        del key
        return False

    def get_global_version(self) -> int:
        """取全局版本号（占位恒 0）。

        Returns:
            int: 恒 0。
        """
        return 0

    async def aget_messages(
        self, tenant: str | None, locale: str, *, version: int
    ) -> ConcurrentStableDict[str, str] | None:
        """读语言包（占位恒未命中）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            version: 当前版本号。

        Returns:
            ConcurrentStableDict[str, str] | None: 恒 None。
        """
        del tenant, locale, version
        return None

    async def aset_messages(
        self,
        tenant: str | None,
        locale: str,
        messages: ConcurrentStableDict[str, str],
        *,
        version: int,
        ttl: int,
    ) -> None:
        """写语言包（占位空操作）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            messages: 文案映射。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        del tenant, locale, messages, version, ttl

    async def adrop_messages(self, tenant: str | None, locale: str) -> None:
        """删语言包缓存（占位空操作）。

        Args:
            tenant: 租户标识。
            locale: 语言。
        """
        del tenant, locale

    async def aget_locales(self, tenant: str | None, *, version: int) -> ConcurrentStableList[LocaleInfo] | None:
        """读语言清单（占位恒未命中）。

        Args:
            tenant: 租户标识。
            version: 当前版本号。

        Returns:
            ConcurrentStableList[LocaleInfo] | None: 恒 None。
        """
        del tenant, version
        return None

    async def aset_locales(
        self, tenant: str | None, locales: ConcurrentStableList[LocaleInfo], *, version: int, ttl: int
    ) -> None:
        """写语言清单（占位空操作）。

        Args:
            tenant: 租户标识。
            locales: 清单条目。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        del tenant, locales, version, ttl

    async def adrop_locales(self, tenant: str | None) -> None:
        """删语言清单缓存（占位空操作）。

        Args:
            tenant: 租户标识。
        """
        del tenant

    async def aversion(self, tenant: str | None) -> int:
        """取当前版本号（占位恒 0）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 恒 0。
        """
        del tenant
        return 0

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增版本号（占位恒 1）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 恒 1。
        """
        del tenant
        return 1


class NullLocaleRegistry(BaseLocaleRegistry, BaseNullObject):
    """占位语言清单：种子语言（`zh-CN` 默认 / `en-US`），RTL 恒否。"""

    async def list_locales(self, *, enabled_only: bool = False) -> ConcurrentStableList[LocaleInfo]:
        """返回种子清单。

        Args:
            enabled_only: 是否只返回启用语言（种子全部启用，等价）。

        Returns:
            ConcurrentStableList[LocaleInfo]: 种子清单条目。
        """
        del enabled_only  # 种子清单全部启用，无需过滤
        return seed_locale_infos()

    async def refresh(self) -> None:
        """把快照重置为种子清单（无 IO）。"""
        self._replace_snapshot(seed_locale_infos())
