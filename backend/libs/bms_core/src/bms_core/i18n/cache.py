"""国际化缓存域（`I18nCacheRegion` 子类）：语言清单 + 语言包两层缓存。

- `MemoryI18nCacheRegion`：纯进程内 L1（版本按租户计数）；无 Redis 环境 / 测试用。
- `RedisI18nCacheRegion`：Redis 共享层（清单键 / 语言包键 / 版本键 `INCR`）叠加进程内 L1（先 L1 后 Redis，
  命中回填）；Redis 不可用时由 `RedisCacheRegion` 内部降级（读未命中 → 回源）。
- **版本化载荷**：载荷统一带 `v`（写入时的版本号），读取时与当前版本比对，不一致即视为未命中并回源——
  跨实例「改完即生效」不依赖 `DEL` 是否成功；`[i18n].version_check=false` 时版本恒 0（退回纯 TTL）。
- 键构成统一由 `I18nCacheRegion`（`messages_cache_key` / `locales_cache_key` / `version_cache_key`）提供，
  实现不重拼 key（规范 `bms:{租户|global}:i18n:{业务键}`）。
"""

from collections.abc import Iterable, Mapping
from typing import cast

from fastapi import Request

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.cache.redis import RedisCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, resolve_plugin
from bms_core.i18n.locale import LocaleInfo

__all__ = [
    "DEFAULT_MAX_ITEMS",
    "I18N_CACHE_DOMAIN",
    "I18nCacheRegion",
    "MemoryI18nCacheRegion",
    "RedisI18nCacheRegion",
    "get_i18n_cache_region",
    "read_locales_payload",
    "read_messages_payload",
]

I18N_CACHE_DOMAIN = "i18n"
"""缓存域简称（key 第二段之后的域位）。"""

DEFAULT_MAX_ITEMS = 64
"""L1 条目上限（LRU）：语言包按语言一条、清单一条，语言数一般不超过 20。"""

PAYLOAD_VERSION = "v"
"""载荷版本字段名。"""

PAYLOAD_MESSAGES = "messages"
"""语言包载荷字段名。"""

PAYLOAD_LOCALES = "locales"
"""语言清单载荷字段名。"""


def build_messages_payload(version: int, messages: ConcurrentStableDict[str, str]) -> object:
    """构造语言包缓存载荷（内置 `dict`，保证 JSON 可往返）。

    Args:
        version: 写入时捕获的版本号（`0` = 不校验版本）。
        messages: 文案映射。

    Returns:
        dict[str, object]: 载荷。
    """
    return {PAYLOAD_VERSION: version, PAYLOAD_MESSAGES: dict(messages)}


def read_messages_payload(raw: object, version: int) -> ConcurrentStableDict[str, str] | None:
    """读语言包缓存载荷（版本不符 / 结构非法按未命中）。

    Args:
        raw: 缓存原始值。
        version: 当前版本号（`0` = 不校验）。

    Returns:
        ConcurrentStableDict[str, str] | None: 文案映射；未命中返回 None。
    """
    if not isinstance(raw, Mapping):
        return None
    payload = cast("Mapping[str, object]", raw)
    if payload.get(PAYLOAD_VERSION) != version:
        return None
    body = payload.get(PAYLOAD_MESSAGES)
    if not isinstance(body, Mapping):
        return None
    return ConcurrentStableDict({str(key): str(value) for key, value in cast("Mapping[object, object]", body).items()})


def build_locales_payload(version: int, locales: ConcurrentStableList[LocaleInfo]) -> object:
    """构造语言清单缓存载荷。

    Args:
        version: 写入时捕获的版本号。
        locales: 清单条目。

    Returns:
        dict[str, object]: 载荷。
    """
    return {
        PAYLOAD_VERSION: version,
        PAYLOAD_LOCALES: [
            {
                "code": item.code,
                "name": item.name,
                "rtl": item.rtl,
                "is_default": item.is_default,
                "status": item.status,
                "sort": item.sort,
            }
            for item in locales
        ],
    }


def read_locales_payload(raw: object, version: int) -> ConcurrentStableList[LocaleInfo] | None:
    """读语言清单缓存载荷（版本不符 / 结构非法按未命中）。

    Args:
        raw: 缓存原始值。
        version: 当前版本号。

    Returns:
        ConcurrentStableList[LocaleInfo] | None: 清单条目；未命中返回 None。
    """
    if not isinstance(raw, Mapping):
        return None
    payload = cast("Mapping[str, object]", raw)
    if payload.get(PAYLOAD_VERSION) != version:
        return None
    body = payload.get(PAYLOAD_LOCALES)
    if not isinstance(body, Iterable) or isinstance(body, str | bytes):
        return None
    result: ConcurrentStableList[LocaleInfo] = ConcurrentStableList()
    for row in cast("Iterable[object]", body):
        if not isinstance(row, Mapping):
            return None
        item = cast("Mapping[str, object]", row)
        code = item.get("code")
        if not isinstance(code, str) or not code:
            return None
        result.add(
            LocaleInfo(
                code=code,
                name=str(item.get("name") or ""),
                rtl=bool(item.get("rtl")),
                is_default=bool(item.get("is_default")),
                status=str(item.get("status") or "enabled"),
                sort=int(cast("int", item.get("sort") or 0)),
            )
        )
    return result


class I18nCacheRegion(CacheRegion):
    """国际化缓存域扩展子类：固定 `domain="i18n"` 并补充清单 / 语言包 key 与版本判定。"""

    key: str = "i18n_cache_region"
    plugin_key: str = "i18n_cache_region"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    def domain(self) -> str:
        """业务域简称（固定 `i18n`）。

        Returns:
            str: 缓存域简称。
        """
        return I18N_CACHE_DOMAIN

    def messages_cache_key(self, tenant: str | None, locale: str) -> str:
        """拼语言包缓存 key（`bms:{tenant}:i18n:messages:{locale}`）。

        Args:
            tenant: 租户标识；None 为全局。
            locale: 语言（调用方已归一为标准形态）。

        Returns:
            str: 缓存 key。
        """
        return self.build_key(f"messages:{locale}", tenant=tenant)

    def locales_cache_key(self, tenant: str | None) -> str:
        """拼语言清单缓存 key（`bms:{tenant}:i18n:locales`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            str: 缓存 key。
        """
        return self.build_key("locales", tenant=tenant)

    def version_cache_key(self, tenant: str | None) -> str:
        """拼版本键（`bms:{tenant}:i18n:version`）。

        Args:
            tenant: 租户标识；None 为全局。

        Returns:
            str: 版本键。
        """
        return self.build_key("version", tenant=tenant)

    async def aget_messages(
        self, tenant: str | None, locale: str, *, version: int
    ) -> ConcurrentStableDict[str, str] | None:
        """读语言包（未命中 / 版本不符返回 None）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            version: 当前版本号（`0` = 不校验）。

        Returns:
            ConcurrentStableDict[str, str] | None: 文案映射。
        """
        raise NotImplementedError

    async def aset_messages(
        self,
        tenant: str | None,
        locale: str,
        messages: ConcurrentStableDict[str, str],
        *,
        version: int,
        ttl: int,
    ) -> None:
        """写语言包（带版本与 TTL）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            messages: 文案映射。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        raise NotImplementedError

    async def adrop_messages(self, tenant: str | None, locale: str) -> None:
        """删语言包缓存。

        Args:
            tenant: 租户标识。
            locale: 语言。
        """
        raise NotImplementedError

    async def aget_locales(self, tenant: str | None, *, version: int) -> ConcurrentStableList[LocaleInfo] | None:
        """读语言清单（未命中 / 版本不符返回 None）。

        Args:
            tenant: 租户标识。
            version: 当前版本号。

        Returns:
            ConcurrentStableList[LocaleInfo] | None: 清单条目。
        """
        raise NotImplementedError

    async def aset_locales(
        self, tenant: str | None, locales: ConcurrentStableList[LocaleInfo], *, version: int, ttl: int
    ) -> None:
        """写语言清单（带版本与 TTL）。

        Args:
            tenant: 租户标识。
            locales: 清单条目。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        raise NotImplementedError

    async def adrop_locales(self, tenant: str | None) -> None:
        """删语言清单缓存。

        Args:
            tenant: 租户标识。
        """
        raise NotImplementedError

    async def aversion(self, tenant: str | None) -> int:
        """取当前版本号。

        Args:
            tenant: 租户标识。

        Returns:
            int: 版本号（缺失按 0）。
        """
        raise NotImplementedError

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增版本号（不设过期）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 递增后的版本号。
        """
        raise NotImplementedError


class MemoryI18nCacheRegion(I18nCacheRegion):
    """国际化缓存·进程内实现（插件名 `memory`）：L1 + 按租户版本。"""

    def __init__(self, *, max_items: int = DEFAULT_MAX_ITEMS) -> None:
        """初始化。

        Args:
            max_items: L1 条目上限（LRU）。
        """
        self._memory = MemoryCacheRegion(domain=I18N_CACHE_DOMAIN, max_items=max_items)
        self._versions: ConcurrentStableDict[str, int] = ConcurrentStableDict()

    def get(self, key: str) -> object | None:
        """读缓存（同步契约，代理 L1）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值。
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
        """取全局版本号（同步契约：全部租户版本求和，仅作一致性提示）。

        Returns:
            int: 版本号。
        """
        return sum(self._versions.values())

    async def aget_messages(
        self, tenant: str | None, locale: str, *, version: int
    ) -> ConcurrentStableDict[str, str] | None:
        """读语言包（L1）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            version: 当前版本号。

        Returns:
            ConcurrentStableDict[str, str] | None: 文案映射。
        """
        return read_messages_payload(self._memory.get(self.messages_cache_key(tenant, locale)), version)

    async def aset_messages(
        self,
        tenant: str | None,
        locale: str,
        messages: ConcurrentStableDict[str, str],
        *,
        version: int,
        ttl: int,
    ) -> None:
        """写语言包（L1）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            messages: 文案映射。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        self._memory.set(self.messages_cache_key(tenant, locale), build_messages_payload(version, messages), ttl)

    async def adrop_messages(self, tenant: str | None, locale: str) -> None:
        """删语言包缓存。

        Args:
            tenant: 租户标识。
            locale: 语言。
        """
        self._memory.delete(self.messages_cache_key(tenant, locale))

    async def aget_locales(self, tenant: str | None, *, version: int) -> ConcurrentStableList[LocaleInfo] | None:
        """读语言清单（L1）。

        Args:
            tenant: 租户标识。
            version: 当前版本号。

        Returns:
            ConcurrentStableList[LocaleInfo] | None: 清单条目。
        """
        return read_locales_payload(self._memory.get(self.locales_cache_key(tenant)), version)

    async def aset_locales(
        self, tenant: str | None, locales: ConcurrentStableList[LocaleInfo], *, version: int, ttl: int
    ) -> None:
        """写语言清单（L1）。

        Args:
            tenant: 租户标识。
            locales: 清单条目。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        self._memory.set(self.locales_cache_key(tenant), build_locales_payload(version, locales), ttl)

    async def adrop_locales(self, tenant: str | None) -> None:
        """删语言清单缓存。

        Args:
            tenant: 租户标识。
        """
        self._memory.delete(self.locales_cache_key(tenant))

    async def aversion(self, tenant: str | None) -> int:
        """取当前版本号。

        Args:
            tenant: 租户标识。

        Returns:
            int: 版本号。
        """
        return int(self._versions.get(self.version_cache_key(tenant)) or 0)

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增版本号。

        Args:
            tenant: 租户标识。

        Returns:
            int: 递增后的版本号。
        """
        key = self.version_cache_key(tenant)
        value = int(self._versions.get(key) or 0) + 1
        self._versions.set(key, value)
        return value


class RedisI18nCacheRegion(I18nCacheRegion):
    """国际化缓存·Redis 实现（插件名 `redis`）：Redis 共享层 + 进程内 L1。"""

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
        self._redis = redis_region or RedisCacheRegion(domain=I18N_CACHE_DOMAIN, url=url)
        self._l1 = MemoryCacheRegion(domain=f"{I18N_CACHE_DOMAIN}-l1", max_items=max_items)

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
            object | None: 缓存值。
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
            int: 版本号。
        """
        return self._redis.get_global_version()

    async def setup(self) -> None:
        """生命周期钩子：预热 Redis 客户端（不建连）。"""
        await self._redis.setup()

    async def aclose(self) -> None:
        """释放 Redis 客户端（幂等）。"""
        await self._redis.aclose()

    async def aget_messages(
        self, tenant: str | None, locale: str, *, version: int
    ) -> ConcurrentStableDict[str, str] | None:
        """读语言包（先 L1 后 Redis，命中回填 L1）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            version: 当前版本号。

        Returns:
            ConcurrentStableDict[str, str] | None: 文案映射。
        """
        key = self.messages_cache_key(tenant, locale)
        hit = read_messages_payload(self._l1.get(key), version)
        if hit is not None:
            return hit
        value = read_messages_payload(await self._redis.aget(key), version)
        if value is not None:
            self._l1.set(key, build_messages_payload(version, value))
        return value

    async def aset_messages(
        self,
        tenant: str | None,
        locale: str,
        messages: ConcurrentStableDict[str, str],
        *,
        version: int,
        ttl: int,
    ) -> None:
        """写语言包（L1 + Redis）。

        Args:
            tenant: 租户标识。
            locale: 语言。
            messages: 文案映射。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        key = self.messages_cache_key(tenant, locale)
        payload = build_messages_payload(version, messages)
        self._l1.set(key, payload, ttl)
        await self._redis.aset(key, payload, ttl)

    async def adrop_messages(self, tenant: str | None, locale: str) -> None:
        """删语言包缓存（L1 + Redis）。

        Args:
            tenant: 租户标识。
            locale: 语言。
        """
        key = self.messages_cache_key(tenant, locale)
        self._l1.delete(key)
        await self._redis.adelete(key)

    async def aget_locales(self, tenant: str | None, *, version: int) -> ConcurrentStableList[LocaleInfo] | None:
        """读语言清单（先 L1 后 Redis）。

        Args:
            tenant: 租户标识。
            version: 当前版本号。

        Returns:
            ConcurrentStableList[LocaleInfo] | None: 清单条目。
        """
        key = self.locales_cache_key(tenant)
        hit = read_locales_payload(self._l1.get(key), version)
        if hit is not None:
            return hit
        value = read_locales_payload(await self._redis.aget(key), version)
        if value is not None:
            self._l1.set(key, build_locales_payload(version, value))
        return value

    async def aset_locales(
        self, tenant: str | None, locales: ConcurrentStableList[LocaleInfo], *, version: int, ttl: int
    ) -> None:
        """写语言清单（L1 + Redis）。

        Args:
            tenant: 租户标识。
            locales: 清单条目。
            version: 当前版本号。
            ttl: 有效期（秒）。
        """
        key = self.locales_cache_key(tenant)
        payload = build_locales_payload(version, locales)
        self._l1.set(key, payload, ttl)
        await self._redis.aset(key, payload, ttl)

    async def adrop_locales(self, tenant: str | None) -> None:
        """删语言清单缓存（L1 + Redis）。

        Args:
            tenant: 租户标识。
        """
        key = self.locales_cache_key(tenant)
        self._l1.delete(key)
        await self._redis.adelete(key)

    async def aversion(self, tenant: str | None) -> int:
        """取当前版本号（Redis）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 版本号（缺失 / 脏值按 0）。
        """
        raw = await self._redis.aget(self.version_cache_key(tenant))
        try:
            return int(cast("int", raw))
        except TypeError, ValueError:
            return 0

    async def aincrease_version(self, tenant: str | None) -> int:
        """递增版本号（Redis `INCR`，不设过期）。

        Args:
            tenant: 租户标识。

        Returns:
            int: 递增后的版本号。
        """
        return await self._redis.aincrease(self.version_cache_key(tenant))


def get_i18n_cache_region(request: Request) -> I18nCacheRegion:
    """依赖注入提供者（应用级单例；公共依赖经 `bms_core.api.deps` 统一导出）。

    Args:
        request: 请求对象（取装配 settings）。

    Returns:
        I18nCacheRegion: 应用装配的国际化缓存域实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "I18nCacheRegion",
        resolve_plugin(
            "i18n_cache_region",
            settings.i18n_cache_region.provider,
            expected_version=I18nCacheRegion.contract_version,
        ),
    )
