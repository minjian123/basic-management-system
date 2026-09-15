"""cache 能力域缺省实现（Null Object）：不缓存、无副作用（05 补缺）。"""

from app.cache.base import CacheRegion
from app.core.capability import BaseNullObject

__all__ = ["NullCacheRegion"]


class NullCacheRegion(CacheRegion, BaseNullObject):
    """占位缓存 Region：读恒未命中、写 / 删空操作、全局版本号恒 0（不连 Redis）。"""

    @property
    def domain(self) -> str:
        """业务域简称（占位固定 `null`）。

        Returns:
            str: 占位域简称。
        """
        return "null"

    def get(self, key: str) -> object | None:
        """读缓存（占位恒未命中）。

        Args:
            key: 缓存 key（占位忽略）。

        Returns:
            object | None: None。
        """
        return None

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（占位空操作）。

        Args:
            key: 缓存 key（占位忽略）。
            value: 缓存值（占位忽略）。
            ttl: 有效期（占位忽略）。
        """

    def delete(self, key: str) -> bool:
        """删缓存（占位恒不存在）。

        Args:
            key: 缓存 key（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    def get_global_version(self) -> int:
        """取全局版本号（占位恒 0）。

        Returns:
            int: 0。
        """
        return 0
