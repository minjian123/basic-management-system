"""WorkerId 租约上下文管理器与就绪校验（03_06 / 需求 03-7）。

三种使用形态，共用同一实现：

- **应用内**：`worker_id_registry` 作为基础能力经插件装配 `setup()`（`service_lifespan`），关闭时
  `aclose()` 释放；就绪校验 `ensure_worker_id_ready()` 由 lifespan 在装配后调用。
- **异步进程**（异步 ops 入口 / 作业 worker）：`async with worker_id_lease(): ...`。
- **同步进程**（同步 ops 入口）：`with worker_id_lease_sync(): ...`。

非应用进程先经 `ensure_shared_redis_client()` 登记进程共享客户端（建连参数仍取自 `[redis]`）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.redis.bootstrap import ensure_shared_redis_client
from bms_core.workerid.base import BaseWorkerIdRegistry
from bms_core.workerid.null import NullWorkerIdRegistry
from bms_core.workerid.redis import RedisWorkerIdRegistry

__all__ = [
    "build_worker_id_registry",
    "ensure_worker_id_ready",
    "worker_id_lease",
    "worker_id_lease_sync",
]


def build_worker_id_registry(settings: Settings) -> BaseWorkerIdRegistry:
    """按 `[worker_id]` 构造实现实例（非应用进程用；应用内走插件装配）。

    Args:
        settings: 应用配置。

    Returns:
        BaseWorkerIdRegistry: 注册实现实例。

    Raises:
        ConfigError: `provider` 取值非法。
    """
    section = settings.worker_id
    provider = (section.provider or "").strip()
    if not section.enabled or provider in ("", "null"):
        return NullWorkerIdRegistry(settings)
    if provider == "redis":
        return RedisWorkerIdRegistry(settings)
    raise ConfigError(f"[worker_id].provider 取值非法：{provider}（允许 redis / null）")


def ensure_worker_id_ready(registry: BaseWorkerIdRegistry) -> None:
    """就绪校验（生产未取到号即拒启）。

    Args:
        registry: 已取号的注册实现。

    Raises:
        ConfigError: 生产环境仍未分配到 WorkerId。
    """
    registry.assert_ready()


def _prepare(settings: Settings, registry: BaseWorkerIdRegistry) -> None:
    """为非应用进程准备共享 Redis 客户端（仅 Redis 实现需要）。

    Args:
        settings: 应用配置。
        registry: 注册实现。
    """
    if isinstance(registry, RedisWorkerIdRegistry):
        ensure_shared_redis_client(settings)


@asynccontextmanager
async def worker_id_lease(settings: Settings | None = None) -> AsyncGenerator[BaseWorkerIdRegistry]:
    """异步租约上下文（取号 → 就绪校验 → 释放）。

    Args:
        settings: 应用配置；None 取全局单例。

    Yields:
        BaseWorkerIdRegistry: 已取号的注册实现。

    Raises:
        ConfigError: 生产环境未取到号。
    """
    resolved = settings if settings is not None else get_settings()
    registry = build_worker_id_registry(resolved)
    _prepare(resolved, registry)
    try:
        await registry.setup()
        ensure_worker_id_ready(registry)
        yield registry
    finally:
        await registry.aclose()


@contextmanager
def worker_id_lease_sync(settings: Settings | None = None) -> Generator[BaseWorkerIdRegistry]:
    """同步租约上下文（同步 ops 入口用）。

    Args:
        settings: 应用配置；None 取全局单例。

    Yields:
        BaseWorkerIdRegistry: 已取号的注册实现。

    Raises:
        ConfigError: 生产环境未取到号。
    """
    resolved = settings if settings is not None else get_settings()
    registry = build_worker_id_registry(resolved)
    _prepare(resolved, registry)
    try:
        registry.acquire()
        ensure_worker_id_ready(registry)
        yield registry
    finally:
        registry.release()
