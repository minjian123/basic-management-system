"""非应用进程的 Redis 共享客户端登记（03_06）。

`ops` 脚本与作业 worker 不经 FastAPI 装配链，`RedisRedisClient.setup()` 不会被调用；凡是需要在
无应用上下文里使用「进程共享 Redis 客户端」的场景（当前为 WorkerId 租约注册），统一先经本函数
把共享实例登记好——**建连参数仍全部取自 `[redis]`，`from_url` 只在 `redis/redis.py` 内出现**。
"""

from __future__ import annotations

from bms_core.core.config import Settings
from bms_core.redis.base import (
    BaseRedisClient,
    current_shared_redis_client,
    set_shared_redis_client,
)
from bms_core.redis.null import NullRedisClient
from bms_core.redis.redis import RedisRedisClient

__all__ = ["ensure_shared_redis_client"]


def ensure_shared_redis_client(settings: Settings) -> BaseRedisClient:
    """确保进程共享 Redis 客户端已登记（幂等：已登记直接复用）。

    Args:
        settings: 应用配置（`[redis]` 分区）。

    Returns:
        BaseRedisClient: 进程共享客户端（`[redis].provider` 非 `redis` 时登记 `null` 实现，
        取客户端按 fail-closed 抛 `RedisUnavailableError`）。
    """
    existing = current_shared_redis_client()
    if existing is not None:
        return existing
    section = settings.redis
    if (section.provider or "").strip() != "redis":
        client: BaseRedisClient = NullRedisClient()
    else:
        client = RedisRedisClient(
            section.url,
            db=section.db,
            pool_size=section.pool_size,
            socket_timeout_ms=section.socket_timeout_ms,
            socket_connect_timeout_ms=section.socket_connect_timeout_ms,
            health_check_interval_s=section.health_check_interval_s,
            key_prefix=section.key_prefix,
        )
    set_shared_redis_client(client)
    return client
