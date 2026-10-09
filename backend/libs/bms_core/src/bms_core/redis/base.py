"""Redis 统一客户端端口与进程共享实例（03_04 / 需求 03-5）。

设计口径：

- **端口**：`BaseRedisClient`（插件键 `redis_client`）暴露「同步客户端 / 异步客户端 / 就绪探测 / 键前缀」，
  实现名 `redis`（真实）与 `null`（未启用）。
- **进程共享**：装配期由 `redis` 实现的 `setup()` 把自身登记为**进程共享实例**
  （`set_shared_redis_client`）；各能力域（缓存 / 字典缓存 / 配置缓存 / 幂等 / 一致性屏障 /
  分布式锁 / 限流 / 会话 / IdP 状态 / 验证码 / 健康检查）统一经 `shared_sync_client` /
  `shared_async_client` 取用 —— **禁止各自 `from_url` 建连**（单进程同步 / 异步各一个连接池）。
- **fail-closed**：共享实例未登记（`provider=null` 或装配未完成）时取客户端即抛
  `RedisUnavailableError`（`10012` / 503），**不静默降级**；可降级域（缓存三域 / 限流）自行兜底。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_MS",
    "DEFAULT_HEALTH_CHECK_INTERVAL_S",
    "DEFAULT_KEY_PREFIX",
    "DEFAULT_SOCKET_TIMEOUT_MS",
    "REDIS_CLIENT_PLUGIN_KEY",
    "BaseRedisClient",
    "clear_shared_redis_client",
    "set_shared_redis_client",
    "shared_async_client",
    "shared_redis_client",
    "shared_sync_client",
]

REDIS_CLIENT_PLUGIN_KEY = "redis_client"
"""插件键（`PLUGIN_WIRINGS` / 配置分区 `[redis]` 的 `provider`）。"""

DEFAULT_KEY_PREFIX = "bms"
"""统一键前缀（键口径 `{前缀}:{租户|global}:{域}:{业务键}`）。"""

DEFAULT_SOCKET_TIMEOUT_MS = 500
"""命令超时缺省（毫秒）——架构要求「Redis 操作短超时快速失败」。"""

DEFAULT_CONNECT_TIMEOUT_MS = 500
"""建连超时缺省（毫秒）。"""

DEFAULT_HEALTH_CHECK_INTERVAL_S = 30
"""连接健康探测间隔缺省（秒）。"""

_SHARED_KEY = "default"
"""共享实例键（进程内唯一）。"""

_SHARED: ConcurrentStableDict[str, BaseRedisClient] = ConcurrentStableDict()
"""进程共享客户端登记表（装配期写入，测试可覆盖）。"""


class BaseRedisClient(BasePluggable, ABC):
    """Redis 统一客户端端口：同步 / 异步客户端访问 + 就绪探测 + 键前缀。"""

    key: str = REDIS_CLIENT_PLUGIN_KEY
    plugin_key: str = REDIS_CLIENT_PLUGIN_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def url(self) -> str:
        """连接串（缺省实现返回空串）。"""

    @property
    @abstractmethod
    def key_prefix(self) -> str:
        """统一键前缀（`bms` 缺省）。"""

    @abstractmethod
    def sync_client(self) -> SyncRedis:
        """取同步客户端（懒建，同一进程复用同一实例）。

        Raises:
            RedisUnavailableError: 未启用 / 不可用（faid-closed）。
        """

    @abstractmethod
    def async_client(self) -> AsyncRedis:
        """取异步客户端（懒建，同一进程复用同一实例）。

        Raises:
            RedisUnavailableError: 未启用 / 不可用（fail-closed）。
        """

    @abstractmethod
    async def ping(self) -> None:
        """就绪探测（`PING`）。

        Raises:
            RedisUnavailableError: 未启用 / 不可用（fail-closed）。
        """


def set_shared_redis_client(client: BaseRedisClient) -> None:
    """登记进程共享客户端（装配期由 `redis` 实现 `setup()` 调用；测试可显式覆盖）。

    Args:
        client: 客户端实现实例。
    """
    _SHARED.set(_SHARED_KEY, client)


def clear_shared_redis_client() -> None:
    """清除共享登记（测试隔离；应用生命周期结束时由实现自身清理）。"""
    _SHARED.get_and_remove(_SHARED_KEY)


def shared_redis_client() -> BaseRedisClient:
    """取进程共享客户端（未登记时返回 `null` 实现 → 取客户端即报 `RedisUnavailableError`）。

    Returns:
        BaseRedisClient: 共享客户端实例。
    """
    existing = _SHARED.get(_SHARED_KEY)
    if existing is not None:
        return existing
    from bms_core.redis.null import NullRedisClient

    return NullRedisClient()


def shared_sync_client() -> SyncRedis:
    """取共享同步客户端。

    Returns:
        SyncRedis: 同步客户端实例。

    Raises:
        RedisUnavailableError: 未启用 / 不可用。
    """
    return shared_redis_client().sync_client()


def shared_async_client() -> AsyncRedis:
    """取共享异步客户端。

    Returns:
        AsyncRedis: 异步客户端实例。

    Raises:
        RedisUnavailableError: 未启用 / 不可用。
    """
    return shared_redis_client().async_client()
