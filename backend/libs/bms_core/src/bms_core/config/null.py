"""config 能力域缺省实现（Null Object）：空取数与空缓存，不连库、不连 Redis。"""

from bms_core.config.base import BaseConfigSource, ConfigCacheRegion
from bms_core.core.capability import BaseNullObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList

__all__ = ["NullConfigCacheRegion", "NullConfigSource"]


class NullConfigSource(BaseConfigSource, BaseNullObject):
    """占位系统参数取数：恒空结果（调用方回落代码默认表）。"""

    async def get_many(self, keys: ConcurrentStableList[str]) -> ConcurrentStableDict[str, str]:
        """批量取参数（占位恒空）。

        Args:
            keys: 参数键序列（插入序；占位忽略）。

        Returns:
            ConcurrentStableDict[str, str]: 空映射。
        """
        return ConcurrentStableDict()


class NullConfigCacheRegion(ConfigCacheRegion, BaseNullObject):
    """占位系统参数缓存域：读恒未命中、写 / 删空操作、全局版本号恒 0。"""

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
