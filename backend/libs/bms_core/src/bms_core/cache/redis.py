"""Redis 缓存 Region（真实实现，redis-py 自写）：同步契约方法 + 异步方法。

- 同步方法（`get` / `set` / `delete` / `get_global_version`）供通用模块与小 IO 场景；异步方法
  （`aget` / `aset` / `adelete` / `aincrease` / `asetnx` / `arelease_lock`）供异步域（字典取数 / 翻译）——
  避免在事件循环内阻塞（正是本实现选 redis-py 而非同步 Region 库的原因，口径回写见 02-13）。
- 值经 JSON 序列化（`default=str`）；反序列化失败按未命中（防脏值）。
- 三防：`ttl_with_jitter`（雪崩）/ `asetnx` 互斥锁（击穿）/ 空值标记由调用方写入（穿透）。
- Redis 不可用（连接或命令异常）统一降级为未命中 / 空操作并记日志，不抛业务错（由域层直连 DB 兜底）。
"""

import json
import random
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from bms_core.cache.base import CacheRegion
from bms_core.core.logging import get_logger

__all__ = ["JITTER_RATIO", "RedisCacheRegion"]

_LOGGER = get_logger("bms")

JITTER_RATIO = 0.1
"""TTL 抖动比例（0 ~ 10%，防雪崩）。"""

_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _dump(value: object) -> str:
    """序列化缓存值（JSON；不可序列化项经 `default=str` 兜底）。

    Args:
        value: 缓存值。

    Returns:
        str: JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, default=str)


def _load(raw: object) -> object | None:
    """反序列化缓存值（失败按未命中）。

    Args:
        raw: Redis 原始值。

    Returns:
        object | None: 缓存值；未命中 / 脏值返回 None。
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class RedisCacheRegion(CacheRegion):
    """Redis Region（插件名 `redis`）：同步契约 + 异步方法。"""

    def __init__(
        self,
        *,
        domain: str = "generic",
        url: str | None = None,
        sync_client: Redis | None = None,
        async_client: AsyncRedis | None = None,
    ) -> None:
        """初始化。

        Args:
            domain: 业务域简称（用于 `build_key` 分域）。
            url: Redis 连接串（缺省由装配工厂取 `settings.redis.url` 注入）。
            sync_client: 同步客户端（测试注入 `fakeredis.FakeRedis`；缺省按 `url` 懒建）。
            async_client: 异步客户端（测试注入 `fakeredis.aioredis.FakeRedis`；缺省按 `url` 懒建）。
        """
        self._domain = domain
        self._url = url
        self._sync = sync_client
        self._async = async_client

    @property
    def domain(self) -> str:
        """业务域简称。

        Returns:
            str: 域简称。
        """
        return self._domain

    @property
    def sync_client(self) -> Redis:
        """同步客户端（懒建）。

        Returns:
            Redis: 同步客户端实例。
        """
        if self._sync is None:
            self._sync = Redis.from_url(self._url or "", decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
        return self._sync

    @property
    def async_client(self) -> AsyncRedis:
        """异步客户端（懒建）。

        Returns:
            AsyncRedis: 异步客户端实例。
        """
        if self._async is None:
            self._async = AsyncRedis.from_url(self._url or "", decode_responses=True)  # pyright: ignore[reportUnknownMemberType]
        return self._async

    def ttl_with_jitter(self, ttl: int | None = None) -> int:
        """返回带随机抖动的 TTL（基础值 + 0 ~ 10%，防雪崩）。

        Args:
            ttl: 基础 TTL（秒）；None 用 `default_ttl`。

        Returns:
            int: 抖动后的 TTL（最小 1）。
        """
        base = self.default_ttl if ttl is None else ttl
        if base <= 0:
            return base
        return base + random.randint(0, max(1, int(base * JITTER_RATIO)))

    async def setup(self) -> None:
        """生命周期钩子：预热客户端（不建连；异常降级）。"""
        self._warmup()

    async def aclose(self) -> None:
        """释放客户端（幂等）。"""
        sync_client, self._sync = self._sync, None
        async_client, self._async = self._async, None
        try:
            if sync_client is not None:
                sync_client.close()
        except Exception as exc:
            self._degrade("close_sync", self._domain, exc)
        try:
            if async_client is not None:
                await async_client.aclose()  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("close_async", self._domain, exc)

    def get(self, key: str) -> object | None:
        """读缓存（同步；失败降级未命中）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        try:
            return _load(self.sync_client.get(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("get", key, exc)
            return None

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（同步；失败降级空操作）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）；None 用 `default_ttl`（含抖动）。
        """
        seconds = self.ttl_with_jitter(ttl)
        try:
            client = self.sync_client
            if seconds > 0:
                client.set(key, _dump(value), ex=seconds)  # pyright: ignore[reportUnknownMemberType]
            else:
                client.set(key, _dump(value))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("set", key, exc)

    def delete(self, key: str) -> bool:
        """删缓存（同步；失败降级 False）。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        try:
            return bool(self.sync_client.delete(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("delete", key, exc)
            return False

    def get_global_version(self) -> int:
        """取全局版本号（同步；失败降级 0）。

        Returns:
            int: 当前版本号。
        """
        try:
            raw = self.sync_client.get(self.build_key("version"))
        except Exception as exc:
            self._degrade("get_version", self._domain, exc)
            return 0
        return _to_int(raw)

    async def aget(self, key: str) -> object | None:
        """读缓存（异步；失败降级未命中）。

        Args:
            key: 缓存 key。

        Returns:
            object | None: 缓存值；未命中返回 None。
        """
        try:
            return _load(await self.async_client.get(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("aget", key, exc)
            return None

    async def aset(self, key: str, value: object, ttl: int | None = None) -> None:
        """写缓存（异步；失败降级空操作）。

        Args:
            key: 缓存 key。
            value: 缓存值。
            ttl: 有效期（秒）；None 用 `default_ttl`（含抖动）。
        """
        seconds = self.ttl_with_jitter(ttl)
        try:
            client = self.async_client
            if seconds > 0:
                await client.set(key, _dump(value), ex=seconds)  # pyright: ignore[reportUnknownMemberType]
            else:
                await client.set(key, _dump(value))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("aset", key, exc)

    async def adelete(self, key: str) -> bool:
        """删缓存（异步；失败降级 False）。

        Args:
            key: 缓存 key。

        Returns:
            bool: 删到为 True。
        """
        try:
            return bool(await self.async_client.delete(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("adelete", key, exc)
            return False

    async def aincrease(self, key: str) -> int:
        """原子自增（异步；版本键 `INCR` 语义；失败降级 0）。

        Args:
            key: 缓存 key。

        Returns:
            int: 自增后的值；失败返回 0。
        """
        try:
            return int(await self.async_client.incr(key))  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("aincrease", key, exc)
            return 0

    async def asetnx(self, key: str, token: str, ttl: int) -> bool:
        """互斥锁获取（`SET key token NX EX ttl`；失败降级 True 放行）。

        Args:
            key: 锁 key。
            token: 持有者令牌（释放时比对）。
            ttl: 锁有效期（秒）。

        Returns:
            bool: 获锁为 True。
        """
        seconds = max(1, ttl)
        try:
            client = self.async_client
            acquired = await client.set(key, token, nx=True, ex=seconds)  # pyright: ignore[reportUnknownMemberType]
            return bool(acquired)
        except Exception as exc:
            self._degrade("asetnx", key, exc)
            return True

    async def arelease_lock(self, key: str, token: str) -> bool:
        """释放互斥锁（Lua 比对 token，避免误删他锁）。

        Args:
            key: 锁 key。
            token: 持有者令牌。

        Returns:
            bool: 释放到为 True。
        """
        try:
            client = self.async_client
            result = await client.eval(_RELEASE_LOCK_LUA, 1, key, token)  # pyright: ignore[reportUnknownMemberType]
            return bool(result)
        except Exception as exc:
            self._degrade("arelease_lock", key, exc)
            return False

    def clear(self) -> None:
        """清空当前库（测试 / 调试用；生产慎用）。"""
        try:
            self.sync_client.flushdb()  # pyright: ignore[reportUnknownMemberType]
        except Exception as exc:
            self._degrade("flushdb", self._domain, exc)

    def _warmup(self) -> None:
        """预热客户端引用（建对象不建连；`url` 缺失时跳过）。"""
        if self._sync is None and self._async is None and self._url:
            _ = self.sync_client
            _ = self.async_client

    def _degrade(self, action: str, key: str, exc: Exception) -> None:
        """记录降级日志（不抛错）。

        Args:
            action: 动作名。
            key: 缓存 key / 域标识。
            exc: 原始异常。
        """
        _LOGGER.warning("缓存降级", action=action, key=key, error=str(exc))


def _to_int(raw: Any) -> int:
    """把 Redis 原始值转为整数（失败 0）。

    Args:
        raw: 原始值。

    Returns:
        int: 整数值。
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        return int(raw)  # pyright: ignore[reportArgumentType]
    except TypeError, ValueError:
        return 0
