"""通用内存缓存 Region（真实实现）：进程内 LRU + TTL + 全局版本号；无 IO、无外部依赖。

- 供无 Redis 环境 / 测试与字典域 L1 使用；真实 Redis 实现见 `app/cache/redis.py`。
- `bump_version` 供写路径同步本进程版本号（Redis 可用时以 Redis 版本键为准，见 `DictCacheRegion`）。
"""

from collections import OrderedDict
from threading import Lock
from time import monotonic

from bms_core.cache.base import CacheRegion

__all__ = ["DEFAULT_MAX_ITEMS", "MemoryCacheRegion"]

DEFAULT_MAX_ITEMS = 1024
"""缺省条目上限（LRU 淘汰）。"""


class MemoryCacheRegion(CacheRegion):
    """通用内存 Region（插件名 `memory`；线程安全）。"""

    def __init__(self, *, domain: str = "memory", max_items: int = DEFAULT_MAX_ITEMS) -> None:
        """初始化。

        Args:
            domain: 业务域简称（用于 `build_key` 分域）。
            max_items: 条目上限（LRU 淘汰；最小 1）。
        """
        self._domain = domain
        self._max_items = max(1, max_items)
        self._items: OrderedDict[str, tuple[object, float | None]] = OrderedDict()
        self._version = 0
        self._lock = Lock()

    @property
    def domain(self) -> str:
        """业务域简称。

        Returns:
            str: 域简称。
        """
        return self._domain

    def get(self, key: str) -> object | None:
        """读缓存（过期即删；命中刷新 LRU）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中 / 过期返回 None。
        """
        now = monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires is not None and expires <= now:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（超出上限淘汰最早写入）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）；None 用 `default_ttl`，0 / 负数表示不过期。
        """
        ttl = self.default_ttl if ttl is None else ttl
        expires = monotonic() + ttl if ttl > 0 else None
        with self._lock:
            self._items[key] = (value, expires)
            self._items.move_to_end(key)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def delete(self, key: str) -> bool:
        """删缓存。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        with self._lock:
            return self._items.pop(key, None) is not None

    def get_global_version(self) -> int:
        """取全局版本号（进程内整数）。

        Returns:
            int: 当前版本号。
        """
        with self._lock:
            return self._version

    def bump_version(self) -> int:
        """递增全局版本号（写路径调用）。

        Returns:
            int: 递增后的版本号。
        """
        with self._lock:
            self._version += 1
            return self._version

    def clear(self) -> None:
        """清空全部条目（版本号不变；测试与失效用）。"""
        with self._lock:
            self._items.clear()
