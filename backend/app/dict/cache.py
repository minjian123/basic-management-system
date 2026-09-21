"""字典域缓存实现（`DictCacheRegion` 子类）：进程内 L1 与 Redis 两层。

- `MemoryDictCacheRegion`：纯进程内 L1（双分区：整类型 + 按值子集；版本按租户计数）；无 Redis 环境 / 测试用。
- `RedisDictCacheRegion`：Redis 共享层（类型 key / 版本键 `INCR` / SETNX 互斥锁 / TTL 抖动）叠加进程内 L1
  （先 L1 后 Redis，命中回填）；Redis 不可用时自动降级（`RedisCacheRegion` 内部兜底）。
- 两层键构成统一由 `DictCacheRegion`（`dict_key` / `value_key` / `version_key`）提供，实现不重拼 key。
"""

from collections.abc import Mapping, Sequence
from threading import Lock
from time import monotonic
from typing import cast

from app.cache.memory import MemoryCacheRegion
from app.cache.redis import RedisCacheRegion
from app.dict.base import DICT_CACHE_DOMAIN, DictCacheRegion

__all__ = ["MemoryDictCacheRegion", "RedisDictCacheRegion"]

DEFAULT_MAX_ITEMS = 1024
"""L1 条目上限（LRU）。"""

DEFAULT_LOCK_TTL = 5
"""互斥锁缺省有效期（秒）。"""


class MemoryDictCacheRegion(DictCacheRegion):
    """字典域内存缓存（插件名 `memory`）：L1 双分区 + 按租户版本 + 进程内锁。"""

    def __init__(self, *, max_items: int = DEFAULT_MAX_ITEMS) -> None:
        """初始化。

        Args:
            max_items: L1 条目上限（LRU；整类型与子集共享）。
        """
        self._memory = MemoryCacheRegion(domain=DICT_CACHE_DOMAIN, max_items=max_items)
        self._versions: dict[str, int] = {}
        self._locks: dict[str, tuple[str, float]] = {}
        self._lock = Lock()

    def get(self, key: str) -> object | None:
        """读缓存（同步契约，代理 L1）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        return self._memory.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（同步契约，代理 L1）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        self._memory.set(key, value, ttl)

    def delete(self, key: str) -> bool:
        """删缓存（同步契约，代理 L1）。

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
            self._versions[tenant or ""] = version
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

    async def alock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
        ttl: int = DEFAULT_LOCK_TTL,
    ) -> bool:
        """获取类型取数互斥锁（进程内；过期自动释放）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。
            ttl: 锁有效期（秒）。

        Returns:
            bool: 获锁为 True。
        """
        key = self.dict_key(tenant, locale, dict_type)
        now = monotonic()
        with self._lock:
            current = self._locks.get(key)
            if current is not None and current[1] > now:
                return False
            self._locks[key] = (token, now + max(1, ttl))
            return True

    async def arelease_lock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
    ) -> bool:
        """释放类型取数互斥锁（比对令牌；令牌不符不删）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。

        Returns:
            bool: 释放到为 True。
        """
        key = self.dict_key(tenant, locale, dict_type)
        with self._lock:
            current = self._locks.get(key)
            if current is None or current[0] != token:
                return False
            del self._locks[key]
            return True


class RedisDictCacheRegion(DictCacheRegion):
    """字典域 Redis 缓存（插件名 `redis`）：Redis 共享层 + 进程内 L1。"""

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
        self._redis = redis_region or RedisCacheRegion(domain=DICT_CACHE_DOMAIN, url=url)
        self._l1 = MemoryCacheRegion(domain=f"{DICT_CACHE_DOMAIN}-l1", max_items=max_items)

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

    async def aget_type(self, tenant: str | None, locale: str, dict_type: str) -> object | None:
        """读类型缓存（先 L1 后 Redis，命中回填 L1）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        key = self.dict_key(tenant, locale, dict_type)
        cached = self._l1.get(key)
        if cached is not None:
            return cached
        value = await self._redis.aget(key)
        if value is not None:
            self._l1.set(key, value)
        return value

    async def aset_type(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        value: object,
        ttl: int | None = None,
    ) -> None:
        """写类型缓存（L1 + Redis）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            value: 缓存值。
            ttl: 有效期（秒）。
        """
        key = self.dict_key(tenant, locale, dict_type)
        self._l1.set(key, value, ttl)
        await self._redis.aset(key, value, ttl)

    async def adrop_type(self, tenant: str | None, locale: str, dict_type: str) -> None:
        """删类型缓存（L1 + Redis）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
        """
        key = self.dict_key(tenant, locale, dict_type)
        self._l1.delete(key)
        await self._redis.adelete(key)

    async def avalue_subset(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        values: Sequence[str],
    ) -> Mapping[str, str]:
        """读按值子集缓存（L1 + Redis）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            values: 待查 value 序列。

        Returns:
            Mapping[str, str]: value → label（仅命中项）。
        """
        key = self.value_key(tenant, locale, dict_type)
        cached = self._l1.get(key)
        if not isinstance(cached, Mapping):
            cached = await self._redis.aget(key)
            if isinstance(cached, Mapping):
                self._l1.set(key, cast("Mapping[str, object]", cached))
        if not isinstance(cached, Mapping):
            return {}
        payload = cast("Mapping[str, object]", cached)
        result: dict[str, str] = {}
        for value in values:
            if value in payload:
                result[value] = str(payload[value])
        return result

    async def aset_value_subset(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        mapping: Mapping[str, str],
    ) -> None:
        """回填按值子集缓存（L1 + Redis 合并写）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            mapping: 待回填的 value → label 映射。
        """
        key = self.value_key(tenant, locale, dict_type)
        cached = self._l1.get(key)
        if not isinstance(cached, Mapping):
            cached = await self._redis.aget(key)
        merged: dict[str, str] = {}
        if isinstance(cached, Mapping):
            payload = cast("Mapping[str, object]", cached)
            merged.update({str(item): str(label) for item, label in payload.items()})
        merged.update({str(item): str(label) for item, label in mapping.items()})
        self._l1.set(key, merged)
        await self._redis.aset(key, merged)

    async def aversion(self, tenant: str | None) -> int:
        """读指定租户版本号（Redis 版本键）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 当前版本号。
        """
        raw = await self._redis.aget(self.version_key(tenant))
        try:
            return int(raw)  # pyright: ignore[reportArgumentType]
        except TypeError, ValueError:
            return 0

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增指定租户版本号（Redis `INCR`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            int: 递增后的版本号。
        """
        return await self._redis.aincrease(self.version_key(tenant))

    async def alock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
        ttl: int = DEFAULT_LOCK_TTL,
    ) -> bool:
        """获取类型取数互斥锁（Redis SETNX）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。
            ttl: 锁有效期（秒）。

        Returns:
            bool: 获锁为 True。
        """
        key = f"lock:{self.dict_key(tenant, locale, dict_type)}"
        return await self._redis.asetnx(key, token, ttl)

    async def arelease_lock(
        self,
        tenant: str | None,
        locale: str,
        dict_type: str,
        token: str,
    ) -> bool:
        """释放类型取数互斥锁（Lua 比对 token）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言。
            dict_type: 字典类型码。
            token: 持有者令牌。

        Returns:
            bool: 释放到为 True。
        """
        key = f"lock:{self.dict_key(tenant, locale, dict_type)}"
        return await self._redis.arelease_lock(key, token)
