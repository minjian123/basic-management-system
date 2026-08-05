"""Redis 异步客户端封装。

- redis.asyncio 统一客户端（集群环境唯一缓存，弃用本地内存缓存）
- 单次操作短超时快速失败（config.toml [redis].timeout，默认 500ms），避免拖垮请求
- Redis key 命名规范：bms:{租户|global}:{域}:{业务键}（见《命名规范》第 10 节）
"""

from __future__ import annotations

from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..core.config import get_settings

logger = structlog.get_logger("bms.db.redis")

_client: Redis | None = None


def get_redis() -> Redis:
    """获取全局 Redis 异步客户端（懒创建，解码响应为字符串）。"""
    global _client
    if _client is None:
        settings = get_settings().redis
        # pyright 对 redis-py 的 **kwargs 参数推断为 Unknown，此处调用参数均为字符串字面量，忽略该提示
        _client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            settings.url, socket_timeout=settings.timeout, decode_responses=True
        )
    return _client


async def close_redis() -> None:
    """关闭全局客户端，应用关闭时调用。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def ping() -> bool:
    """Redis 连通性检查（供 /readyz 使用）；失败返回 False 并记 WARNING。"""
    try:
        # pyright 对 redis-py 方法签名推断 Unknown，忽略该提示
        result: Any = await get_redis().ping()  # pyright: ignore[reportUnknownMemberType]
        return bool(result)
    except RedisError:
        logger.warning("redis ping failed", url=get_settings().redis.url)
        return False
