"""Redis 统一客户端真实实现 `RedisRedisClient`（插件名 `redis`，03_04 / 需求 03-5）。

- **单进程共享**：同步 / 异步各一个客户端（内部各含一个连接池），十个能力域复用，
  **不再各自 `from_url`**；`setup()` 把自身登记为进程共享实例。
- **配置唯一来源**：连接参数全部取自 `[redis]`（`url` / `db` / `pool_size` /
  `socket_timeout_ms` / `socket_connect_timeout_ms` / `health_check_interval_s` / `key_prefix`）。
- **短超时**：`socket_timeout` / `socket_connect_timeout` 缺省 500ms（架构要求快速失败）。
- 惰性建连（`setup()` 不建连、不校验连通性）；连通性由健康检查项 `ping()` 承担。
"""

from __future__ import annotations

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.logging import get_logger
from bms_core.redis.base import (
    DEFAULT_CONNECT_TIMEOUT_MS,
    DEFAULT_HEALTH_CHECK_INTERVAL_S,
    DEFAULT_KEY_PREFIX,
    DEFAULT_SOCKET_TIMEOUT_MS,
    BaseRedisClient,
    clear_shared_redis_client,
    set_shared_redis_client,
    shared_redis_client,
)

__all__ = ["RedisRedisClient"]

_LOGGER = get_logger("bms")


class RedisRedisClient(BaseRedisClient, BaseAsyncResource):
    """Redis 统一客户端（插件名 `redis`）：单进程共享同步 / 异步客户端。"""

    plugin_name = "redis"

    def __init__(
        self,
        url: str,
        *,
        db: int | None = None,
        pool_size: int = 0,
        socket_timeout_ms: int = DEFAULT_SOCKET_TIMEOUT_MS,
        socket_connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
        health_check_interval_s: int = DEFAULT_HEALTH_CHECK_INTERVAL_S,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        sync_client: SyncRedis | None = None,
        async_client: AsyncRedis | None = None,
    ) -> None:
        """初始化（惰性建连，不校验连通性）。

        Args:
            url: 连接串（`[redis].url`）。
            db: 库号覆盖（非 `None` 时覆盖 url 中的库号）。
            pool_size: 连接池上限（0 = 客户端默认）。
            socket_timeout_ms: 命令超时（毫秒）。
            socket_connect_timeout_ms: 建连超时（毫秒）。
            health_check_interval_s: 连接健康探测间隔（秒）。
            key_prefix: 统一键前缀（校验用）。
            sync_client: 注入的同步客户端（测试用）。
            async_client: 注入的异步客户端（测试用）。
        """
        self._url = url
        self._db = db
        self._pool_size = pool_size
        self._socket_timeout_s = max(0.001, socket_timeout_ms / 1000)
        self._connect_timeout_s = max(0.001, socket_connect_timeout_ms / 1000)
        self._health_check_interval_s = max(0, health_check_interval_s)
        self._key_prefix = key_prefix
        self._sync = sync_client
        self._async = async_client

    @property
    def url(self) -> str:
        """连接串。"""
        return self._url

    @property
    def key_prefix(self) -> str:
        """统一键前缀。"""
        return self._key_prefix

    @property
    def _max_connections(self) -> int | None:
        """连接池上限（0 = 客户端默认 → None）。

        Returns:
            int | None: 上限值。
        """
        return self._pool_size if self._pool_size > 0 else None

    def sync_client(self) -> SyncRedis:
        """取共享同步客户端（懒建，连接参数全取 `[redis]`）。

        Returns:
            SyncRedis: 同步客户端实例。
        """
        if self._sync is None:
            self._sync = SyncRedis.from_url(  # pyright: ignore[reportUnknownMemberType]
                self._url,
                decode_responses=True,
                socket_timeout=self._socket_timeout_s,
                socket_connect_timeout=self._connect_timeout_s,
                health_check_interval=self._health_check_interval_s,
                db=self._db,
                max_connections=self._max_connections,
            )
        return self._sync

    def async_client(self) -> AsyncRedis:
        """取共享异步客户端（懒建，连接参数全取 `[redis]`）。

        Returns:
            AsyncRedis: 异步客户端实例。
        """
        if self._async is None:
            self._async = AsyncRedis.from_url(  # pyright: ignore[reportUnknownMemberType]
                self._url,
                decode_responses=True,
                socket_timeout=self._socket_timeout_s,
                socket_connect_timeout=self._connect_timeout_s,
                health_check_interval=self._health_check_interval_s,
                db=self._db,
                max_connections=self._max_connections,
            )
        return self._async

    async def setup(self) -> None:
        """生命周期钩子：登记为进程共享客户端（不建连）。"""
        set_shared_redis_client(self)
        _LOGGER.info("redis_client_ready", url=self._url, key_prefix=self._key_prefix)

    async def ping(self) -> None:
        """就绪探测（异步 `PING`）。"""
        await self.async_client().ping()  # pyright: ignore[reportUnknownMemberType]

    async def aclose(self) -> None:
        """释放同步 / 异步客户端（幂等）。"""
        sync_client, self._sync = self._sync, None
        async_client, self._async = self._async, None
        if sync_client is not None:
            try:
                sync_client.close()
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("redis_sync_close_failed", error=repr(exc))
        if async_client is not None:
            try:
                await async_client.aclose()  # pyright: ignore[reportUnknownMemberType]
            except Exception as exc:  # pragma: no cover - 关闭失败仅日志
                _LOGGER.warning("redis_async_close_failed", error=repr(exc))
        if shared_redis_client() is self:
            clear_shared_redis_client()
