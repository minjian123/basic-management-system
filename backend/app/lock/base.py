"""分布式锁能力域：跨实例互斥基座契约（真实 Redis SETNX 随六 通用能力阶段回补）。

- `BaseDistributedLock`：能力域中间层契约（`key = "distributed_lock"`）——`acquire`（带 TTL，成功返回锁令牌）
  / `release`（按令牌释放，防误放）/ `extend`（续租）；`hold` 提供异步上下文（进入获取、退出释放）。
- `NullDistributedLock`：占位实现，恒定获取成功（不连 Redis），释放 / 续租恒定成功。
- `build_lock_key`：锁 key 统一拼接（`bms:{租户|global}:lock:{资源}`，见《架构设计 · 数据架构》「key 空间规划」节）。
- `get_distributed_lock`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

与进程内锁原语（`app/core/locking.py` 的 `LockStrategy` / `ReadWriteLock` / `LockGuard`）分工：本基座管
**跨实例互斥**（多副本），进程内并发仍走核心原语；互斥场景可叠加使用（如引擎创建防重）。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast
from uuid import uuid4

from fastapi import Request

from app.core.capability import BaseNullObject
from app.core.exceptions import ConcurrentConflictError
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

LOCK_KEY_PREFIX = "bms"
"""锁 key 前缀（与缓存 key 同前缀）。"""

GLOBAL_LOCK_SCOPE = "global"
"""全局锁作用域位（无租户维度的锁）。"""

DEFAULT_LOCK_TTL = 30
"""默认锁 TTL（秒）；真实实现写入 Redis 过期时间，防死锁。"""

DEFAULT_WAIT = 0.0
"""默认等待时长（秒）；0 表示不等待、立即返回。"""


def build_lock_key(*, tenant: str | None, resource: str) -> str:
    """构建锁 key（规范 `bms:{租户|global}:lock:{资源}`）。

    Args:
        tenant: 租户标识；None 表示全局锁。
        resource: 资源标识（如 `engine:create`、`ddl:sys_user`）。

    Returns:
        str: 锁 key。
    """
    return f"{LOCK_KEY_PREFIX}:{tenant or GLOBAL_LOCK_SCOPE}:lock:{resource}"


class BaseDistributedLock(BasePluggable, ABC):
    """分布式锁契约：跨实例互斥（获取 / 释放 / 续租 + 异步上下文）。"""

    key: str = "distributed_lock"
    plugin_key: str = "distributed_lock"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """获取锁。

        Args:
            key: 锁 key（经 `build_lock_key` 构建）。
            ttl: 锁 TTL（秒）；到期自动释放，防死锁。
            wait: 等待时长（秒）；0 表示不等待、立即返回。

        Returns:
            str | None: 锁令牌（释放 / 续租凭据）；未取到返回 None。
        """

    @abstractmethod
    async def release(self, key: str, token: str) -> bool:
        """释放锁（按令牌校验，防误放他人锁）。

        Args:
            key: 锁 key。
            token: `acquire` 返回的锁令牌。

        Returns:
            bool: 释放成功为 True；非持有者（令牌不匹配）为 False。
        """

    @abstractmethod
    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """续租（重置 TTL）。

        Args:
            key: 锁 key。
            token: `acquire` 返回的锁令牌。
            ttl: 新的 TTL（秒）。

        Returns:
            bool: 续租成功为 True；非持有者为 False。
        """

    @asynccontextmanager
    async def hold(
        self,
        key: str,
        *,
        ttl: int = DEFAULT_LOCK_TTL,
        wait: float = DEFAULT_WAIT,
    ) -> AsyncGenerator[str]:
        """持有锁的异步上下文：进入获取、退出释放。

        Args:
            key: 锁 key（经 `build_lock_key` 构建）。
            ttl: 锁 TTL（秒）。
            wait: 等待时长（秒）；0 表示不等待。

        Yields:
            str: 锁令牌。

        Raises:
            ConcurrentConflictError: 未取到锁（10004 / 409），临界区不执行。
        """
        token = await self.acquire(key, ttl=ttl, wait=wait)
        if token is None:
            raise ConcurrentConflictError(f"获取分布式锁失败：{key}")
        try:
            yield token
        finally:
            await self.release(key, token)


class NullDistributedLock(BaseDistributedLock, BaseNullObject):
    """占位分布式锁：恒定获取成功（不连 Redis），释放 / 续租恒定成功。"""

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """恒定返回锁令牌（占位不连 Redis、不写入任何存储）。

        Args:
            key: 锁 key（占位不区分）。
            ttl: 锁 TTL（占位忽略）。
            wait: 等待时长（占位忽略）。

        Returns:
            str | None: 新生成的锁令牌（UUID4 十六进制串）。
        """
        return uuid4().hex

    async def release(self, key: str, token: str) -> bool:
        """恒定释放成功（占位不校验令牌）。

        Args:
            key: 锁 key（占位不区分）。
            token: 锁令牌（占位不校验）。

        Returns:
            bool: True。
        """
        return True

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """恒定续租成功（占位不校验令牌）。

        Args:
            key: 锁 key（占位不区分）。
            token: 锁令牌（占位不校验）。
            ttl: 新的 TTL（占位忽略）。

        Returns:
            bool: True。
        """
        return True


def get_distributed_lock(request: Request) -> BaseDistributedLock:
    """取应用级分布式锁（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseDistributedLock: 应用装配的锁实例。
    """
    return cast("BaseDistributedLock", request.app.state.distributed_lock)
