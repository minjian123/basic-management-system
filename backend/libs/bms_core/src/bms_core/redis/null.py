"""Redis 统一客户端缺省实现 `NullRedisClient`（插件名 `null`，03_04 / 需求 03-5）。

缺省实现**不静默降级**：取客户端 / 探测即抛 `RedisUnavailableError`（`10012` / 503）——
把 Redis 视为基础（必需）能力，未启用时应显式失败而不是让业务「以为去了重 / 以为已生效」。
可降级域（缓存三域 / 限流）自行捕获该异常并回落来源 / 进程内实现。
"""

from __future__ import annotations

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import RedisUnavailableError
from bms_core.redis.base import DEFAULT_KEY_PREFIX, BaseRedisClient

__all__ = ["NullRedisClient"]

_UNAVAILABLE_MESSAGE = "Redis 为基础能力，当前未启用（provider=null）或共享客户端未就绪"


class NullRedisClient(BaseRedisClient, BaseNullObject):
    """Redis 缺省实现：取客户端即报错（fail-closed）。"""

    plugin_name = "null"

    @property
    def url(self) -> str:
        """连接串（缺省实现为空）。"""
        return ""

    @property
    def key_prefix(self) -> str:
        """统一键前缀（缺省值）。"""
        return DEFAULT_KEY_PREFIX

    def sync_client(self) -> SyncRedis:
        """取同步客户端（恒失败）。

        Raises:
            RedisUnavailableError: 恒抛（未启用）。
        """
        raise RedisUnavailableError(_UNAVAILABLE_MESSAGE, data={"provider": self.plugin_name})

    def async_client(self) -> AsyncRedis:
        """取异步客户端（恒失败）。

        Raises:
            RedisUnavailableError: 恒抛（未启用）。
        """
        raise RedisUnavailableError(_UNAVAILABLE_MESSAGE, data={"provider": self.plugin_name})

    async def ping(self) -> None:
        """就绪探测（恒失败）。

        Raises:
            RedisUnavailableError: 恒抛（未启用）。
        """
        raise RedisUnavailableError(_UNAVAILABLE_MESSAGE, data={"provider": self.plugin_name})
