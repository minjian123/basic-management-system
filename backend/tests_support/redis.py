"""测试用 Redis 共享客户端（fakeredis 承载；单测零外部依赖，03_04）。

- 单测默认**不连真 Redis**：夹具装入本模块的假共享客户端后，各能力域（默认取共享客户端）
  自动落到 fakeredis；用例亦可继续显式 `client=` 注入自建 fakeredis 实例。
- 真实 Redis 集成用例仍走 `BMS_TEST_REDIS_URL`（未配置即 skip）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import fakeredis
import fakeredis.aioredis

from bms_core.redis.base import (
    DEFAULT_KEY_PREFIX,
    BaseRedisClient,
    clear_shared_redis_client,
    set_shared_redis_client,
)

__all__ = ["FakeSharedRedisClient", "install_fake_redis_client", "install_process_fake_redis_client"]


class FakeSharedRedisClient(BaseRedisClient):
    """fakeredis 承载的共享客户端（同步 / 异步各一实例，支持 Lua）。"""

    plugin_name = "fake"

    def __init__(self, *, key_prefix: str = DEFAULT_KEY_PREFIX) -> None:
        """初始化。

        Args:
            key_prefix: 统一键前缀。
        """
        self._key_prefix = key_prefix
        self._sync = fakeredis.FakeRedis(decode_responses=True)
        self._async = fakeredis.aioredis.FakeRedis(decode_responses=True)

    @property
    def url(self) -> str:
        """连接串（假实现为空）。"""
        return ""

    @property
    def key_prefix(self) -> str:
        """统一键前缀。"""
        return self._key_prefix

    def sync_client(self) -> Any:
        """取同步 fake 客户端。

        Returns:
            Any: `fakeredis.FakeRedis` 实例。
        """
        return self._sync

    def async_client(self) -> Any:
        """取异步 fake 客户端。

        Returns:
            Any: `fakeredis.aioredis.FakeRedis` 实例。
        """
        return self._async

    async def ping(self) -> None:
        """就绪探测（fake 恒成功）。"""
        await self._async.ping()


def install_process_fake_redis_client(*, key_prefix: str = DEFAULT_KEY_PREFIX) -> FakeSharedRedisClient:
    """进程级装入假共享客户端（幂等；单测夹具调用，不自动清理）。

    用于「装配期把真客户端登记为共享」的场景：测试夹具显式关闭 `[redis].provider` 后，
    以此顶替共享实例，使健康检查 / 直接构造的 Redis 实现落到 fakeredis。

    Args:
        key_prefix: 统一键前缀。

    Returns:
        FakeSharedRedisClient: 假客户端实例。
    """
    client = FakeSharedRedisClient(key_prefix=key_prefix)
    set_shared_redis_client(client)
    return client


@contextmanager
def install_fake_redis_client(*, key_prefix: str = DEFAULT_KEY_PREFIX) -> Iterator[FakeSharedRedisClient]:
    """装入假共享客户端（退出时清除登记，保证用例隔离）。

    Args:
        key_prefix: 统一键前缀。

    Yields:
        FakeSharedRedisClient: 假客户端实例。
    """
    client = FakeSharedRedisClient(key_prefix=key_prefix)
    set_shared_redis_client(client)
    try:
        yield client
    finally:
        clear_shared_redis_client()
