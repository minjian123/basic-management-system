"""config 域缓存实现（`ConfigCacheRegion` 子类）：进程内 L1 与 Redis 两层。

- `MemoryConfigCacheRegion`：纯进程内（值 + 按租户版本）；无 Redis 环境 / 测试用。
- `RedisConfigCacheRegion`：Redis 共享层（值 key / 版本键 `INCR`）叠加进程内 L1（先 L1 后 Redis，命中回填）；
  Redis 不可用时由 `RedisCacheRegion` 内部兜底（读写不中断）。
"""

from threading import Lock

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.cache.redis import RedisCacheRegion
from bms_core.config.base import CONFIG_CACHE_DOMAIN, ConfigCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict

__all__ = ["MemoryConfigCacheRegion", "RedisConfigCacheRegion"]

DEFAULT_MAX_ITEMS = 1024
"""L1 条目上限（LRU）。"""


class MemoryConfigCacheRegion(ConfigCacheRegion):
    """系统参数内存缓存（插件名 `memory`）：值 + 按租户版本。"""

    def __init__(self, *, max_items: int = DEFAULT_MAX_ITEMS) -> None:
        """初始化。

        Args:
            max_items: L1 条目上限（LRU）。
        """
        self._memory = MemoryCacheRegion(domain=CONFIG_CACHE_DOMAIN, max_items=max_items)
        self._versions: ConcurrentStableDict[str, int] = ConcurrentStableDict()
        self._lock = Lock()

    def get(self, key: str) -> object | None:
        """读缓存（同步契约，代理内存区）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        return self._memory.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（同步契约，代理内存区）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        self._memory.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """删缓存（同步契约，代理内存区）。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        return self._memory.delete(key)

    def get_global_version(self) -> int:
        """取全局版本号（进程内整数，缺省租户位）。

        Returns:
            int: 当前版本号。
        """
        return self._memory.get_global_version()

    def bump_version(self, tenant: str | None = None) -> int:
        """递增指定租户版本号（写路径同步调用）。

        Args:
            tenant: 租户标识；None 为缺省租户位。

        Returns:
            int: 递增后的版本号。
        """
        with self._lock:
            version = self._versions.get(tenant or "", 0) + 1
            self._versions.set(tenant or "", version)
        self._memory.bump_version()
        return version

    async def aversion(self, tenant: str | None) -> int:
        """读指定租户版本号。

        Args:
            tenant: 租户标识；None 为缺省租户位。

        Returns:
            int: 当前版本号。
        """
        with self._lock:
            return self._versions.get(tenant or "", 0)

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增指定租户版本号。

        Args:
            tenant: 租户标识；None 为缺省租户位。

        Returns:
            int: 递增后的版本号。
        """
        return self.bump_version(tenant)


class RedisConfigCacheRegion(ConfigCacheRegion):
    """系统参数 Redis 缓存（插件名 `redis`）：Redis 共享层 + 进程内 L1。"""

    def __init__(
        self,
        *,
        url: str | None = None,
        max_items: int = DEFAULT_MAX_ITEMS,
        redis_region: RedisCacheRegion | None = None,
    ) -> None:
        """初始化。

        Args:
            url: Redis 连接串（缺省由装配工厂注入 `settings.redis.url`）。
            max_items: L1 条目上限（LRU）。
            redis_region: Redis 区域（测试注入；缺省按 `url` 构造）。
        """
        self._redis = redis_region or RedisCacheRegion(domain=CONFIG_CACHE_DOMAIN, url=url)
        self._l1 = MemoryCacheRegion(domain=f"{CONFIG_CACHE_DOMAIN}-l1", max_items=max_items)

    @property
    def redis_region(self) -> RedisCacheRegion:
        """Redis 共享层（供写路径 `DEL` / `INCR`）。

        Returns:
            RedisCacheRegion: Redis 区域实例。
        """
        return self._redis

    def get(self, key: str) -> object | None:
        """读缓存（同步契约：先 L1 后 Redis，回填 L1）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        cached = self._l1.get(key)
        if cached is not None:
            return cached
        value = self._redis.get(key)
        if value is not None:
            self._l1.set(key, value)
        return value

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（同步契约：L1 + Redis）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        self._l1.set(key, value, ttl)
        self._redis.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """删缓存（同步契约：L1 + Redis）。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        removed = self._l1.delete(key)
        return self._redis.delete(key) or removed

    def get_global_version(self) -> int:
        """取全局版本号（同步契约：Redis 优先）。

        Returns:
            int: 当前版本号。
        """
        return self._redis.get_global_version()

    async def setup(self) -> None:
        """生命周期钩子：预热 Redis 客户端（不建连）。"""
        await self._redis.setup()

    async def aclose(self) -> None:
        """释放 Redis 客户端（幂等）。"""
        await self._redis.aclose()

    async def aget_value(self, tenant: str | None, config_key: str) -> str | None:
        """读参数缓存（先 L1 后 Redis，命中回填 L1）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。

        Returns:
            str | None: 命中值；未命中返回 None。
        """
        key = self.config_key(tenant, config_key)
        cached = self._l1.get(key)
        if cached is not None:
            return cached if isinstance(cached, str) else None
        value = await self._redis.aget(key)
        if value is not None:
            self._l1.set(key, value)
        return value if isinstance(value, str) else None

    async def aset_value(self, tenant: str | None, config_key: str, value: str, ttl: int | None = None) -> None:
        """写参数缓存（L1 + Redis）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。
            value: 参数值。
            ttl: 有效期（秒）。
        """
        key = self.config_key(tenant, config_key)
        self._l1.set(key, value, ttl)
        await self._redis.aset(key, value, ttl)

    async def adrop_value(self, tenant: str | None, config_key: str) -> None:
        """删参数缓存（L1 + Redis）。

        Args:
            tenant: 租户标识；None 为全局。
            config_key: 参数键。
        """
        key = self.config_key(tenant, config_key)
        self._l1.delete(key)
        await self._redis.adelete(key)

    async def aversion(self, tenant: str | None) -> int:
        """读指定租户版本号（Redis 版本键）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 当前版本号。
        """
        raw = await self._redis.aget(self.version_key(tenant))
        if isinstance(raw, bool):
            return 0
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.lstrip("-").isdigit():
            return int(raw)
        return 0

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增指定租户版本号（Redis `INCR`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 递增后的版本号。
        """
        return await self._redis.aincrease(self.version_key(tenant))
