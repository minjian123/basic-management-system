"""Redis 基础能力域（03_04 / 需求 03-5）：统一客户端端口、进程共享实例与键前缀口径。

对外导出：端口 `BaseRedisClient`、真实实现 `RedisRedisClient`、缺省实现 `NullRedisClient`
与共享取用函数（`shared_sync_client` / `shared_async_client` / `shared_redis_client`）。
"""

from bms_core.redis.base import (
    DEFAULT_CONNECT_TIMEOUT_MS,
    DEFAULT_HEALTH_CHECK_INTERVAL_S,
    DEFAULT_KEY_PREFIX,
    DEFAULT_SOCKET_TIMEOUT_MS,
    REDIS_CLIENT_PLUGIN_KEY,
    BaseRedisClient,
    clear_shared_redis_client,
    set_shared_redis_client,
    shared_async_client,
    shared_redis_client,
    shared_sync_client,
)
from bms_core.redis.null import NullRedisClient
from bms_core.redis.redis import RedisRedisClient

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_MS",
    "DEFAULT_HEALTH_CHECK_INTERVAL_S",
    "DEFAULT_KEY_PREFIX",
    "DEFAULT_SOCKET_TIMEOUT_MS",
    "REDIS_CLIENT_PLUGIN_KEY",
    "BaseRedisClient",
    "NullRedisClient",
    "RedisRedisClient",
    "clear_shared_redis_client",
    "set_shared_redis_client",
    "shared_async_client",
    "shared_redis_client",
    "shared_sync_client",
]
