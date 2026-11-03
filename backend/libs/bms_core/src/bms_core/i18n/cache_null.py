"""国际化缓存域缺省实现（Null Object）：不缓存、版本恒 0，读写全部为空操作。

语义：读一律未命中（每次回源库）、写与删为空、`aversion` 返回 0、`aincrease_version` 返回 1。
用于无 Redis 且未显式选择 `memory` 的环境与契约测试——正确性不受影响（只是少一层缓存）。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.i18n.cache import I18nCacheRegion
from bms_core.i18n.locale import LocaleInfo

__all__ = ["NullI18nCacheRegion"]


class NullI18nCacheRegion(I18nCacheRegion, BaseNullObject):
    """占位国际化缓存：不存储任何键。"""

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
