"""多租户引擎注册表：`{db_key → AsyncEngine}` 生命周期管理。

- 平台引擎常驻；租户引擎懒加载、LRU 闲置回收（默认 30 分钟；每次访问先清扫）。
- 读写角色：写路径返回主引擎；`read_only=True` 经工厂取副本（轮询 / 回退主），
  注册表仍按 `db_key` 跟踪使用时间与逐出（一次释放该库主 + 副本引擎）。
- 并发保护：创建窗口「进程内 `asyncio.Lock` + 跨实例分布式锁」双重互斥（锁经分布式锁
  能力域，缺省 null 实现不连 Redis）；创建失败快速失败。
- 连接预算：`check_connection_budget`（单库口径）+ `tenant_pool_budget_warnings`（按活跃引擎数）。
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.capability import BaseAsyncResource
from app.core.config import Settings
from app.db.engine import EngineFactory
from app.lock.base import DEFAULT_LOCK_TTL, BaseDistributedLock, build_lock_key

PLATFORM_DB_KEY = "platform"
_MAX_ACTIVE_DEFAULT = 32
_IDLE_TIMEOUT_DEFAULT = 1800.0
_CONNECTION_BUDGET_RATIO = 0.7


class EngineRegistry(BaseAsyncResource):
    """异步引擎注册表：平台常驻 + 租户懒加载 + LRU 回收 + 跨实例创建锁。"""

    def __init__(
        self,
        factory: EngineFactory,
        *,
        max_active: int = _MAX_ACTIVE_DEFAULT,
        idle_timeout: float = _IDLE_TIMEOUT_DEFAULT,
        lock: BaseDistributedLock | None = None,
    ) -> None:
        """初始化。

        Args:
            factory: 引擎工厂。
            max_active: 租户引擎活跃上限。
            idle_timeout: 闲置回收阈值（秒）。
            lock: 跨实例分布式锁（None 表示仅进程内锁）。
        """
        self._factory = factory
        self._max_active = max_active
        self._idle_timeout = idle_timeout
        self._lock = lock
        self._engines: dict[str, AsyncEngine] = {}
        self._last_used: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, db_key: str = PLATFORM_DB_KEY, *, read_only: bool = False) -> AsyncEngine:
        """取 / 建引擎（平台常驻、租户懒加载）并刷新使用时间。

        每次访问先清扫闲置租户引擎；创建窗口内先按活跃上限 LRU 逐出，再在
        进程内锁与跨实例锁内建引擎。

        Args:
            db_key: 数据源键。
            read_only: 是否只读；True 时经工厂取副本引擎（无副本回落主引擎）。

        Returns:
            AsyncEngine: 异步引擎。

        Raises:
            ConcurrentConflictError: 跨实例锁未取到（10004 / 409；null 实现不触发）。
        """
        await self._sweep_idle()
        engine = self._engines.get(db_key)
        if engine is None:
            async with self._lock_for(db_key), self._cross_instance_guard(db_key):
                engine = self._engines.get(db_key)
                if engine is None:
                    await self._evict()
                    engine = self._factory.create(db_key)
                    self._engines[db_key] = engine
        self._touch(db_key)
        if read_only:
            return self._factory.create(db_key, read_only=True)
        return engine

    async def release(self, db_key: str) -> None:
        """强制回收指定引擎（如租户停用）。

        Args:
            db_key: 数据源键。
        """
        if db_key == PLATFORM_DB_KEY:
            return
        await self._dispose(db_key)

    def active_keys(self) -> list[str]:
        """当前活跃 `db_key` 列表（含平台）。

        Returns:
            list[str]: 数据源键列表。
        """
        return list(self._engines)

    def redis_lock_key(self, db_key: str) -> str:
        """跨实例创建锁键（经锁基座 key 规范：`bms:global:lock:engine:{db_key}`）。

        Args:
            db_key: 数据源键。

        Returns:
            str: 锁 key。
        """
        return build_lock_key(tenant=None, resource=f"engine:{db_key}")

    @staticmethod
    def check_connection_budget(
        *,
        workers: int,
        pool_size: int,
        max_overflow: int,
        max_connections: int,
    ) -> bool:
        """连接预算校验：`workers × (pool_size + max_overflow) ≤ max_connections × 70%`。

        Args:
            workers: worker 数。
            pool_size: 连接池大小。
            max_overflow: 溢出连接数。
            max_connections: 数据库最大连接数。

        Returns:
            bool: 预算内 True。
        """
        return workers * (pool_size + max_overflow) <= max_connections * _CONNECTION_BUDGET_RATIO

    async def aclose(self) -> None:
        """释放全部引擎（幂等）。"""
        await self._factory.aclose()
        self._engines.clear()
        self._last_used.clear()
        self._locks.clear()

    def _touch(self, db_key: str) -> None:
        """刷新引擎使用时间。"""
        self._last_used[db_key] = time.monotonic()

    def _lock_for(self, db_key: str) -> asyncio.Lock:
        """取（或建）该数据源的进程内创建锁。"""
        lock = self._locks.get(db_key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[db_key] = lock
        return lock

    @asynccontextmanager
    async def _cross_instance_guard(self, db_key: str) -> AsyncGenerator[None]:
        """跨实例创建锁（分布式锁缺省 null 实现时为空操作）。

        Raises:
            ConcurrentConflictError: 锁未取到（不等待）。
        """
        if self._lock is None:
            yield
            return
        async with self._lock.hold(self.redis_lock_key(db_key), ttl=DEFAULT_LOCK_TTL, wait=0):
            yield

    async def _sweep_idle(self) -> None:
        """访问清扫：超闲置阈值的租户引擎 dispose 回收（平台引擎不回收）。"""
        now = time.monotonic()
        for db_key in list(self._engines):
            if db_key == PLATFORM_DB_KEY:
                continue
            if now - self._last_used.get(db_key, now) > self._idle_timeout:
                await self._dispose(db_key)

    async def _evict(self) -> None:
        """按活跃上限逐出最久未用租户引擎（创建窗口内调用）。"""
        tenants = [key for key in self._engines if key != PLATFORM_DB_KEY]
        while len(tenants) >= self._max_active:
            oldest = min(tenants, key=lambda key: self._last_used.get(key, 0.0))
            await self._dispose(oldest)
            tenants.remove(oldest)

    async def _dispose(self, db_key: str) -> None:
        """释放并移除单个引擎。"""
        self._last_used.pop(db_key, None)
        await self._factory.drop(db_key)
        self._engines.pop(db_key, None)


def pool_budget_warnings(settings: Settings) -> list[str]:
    """计算各库连接预算告警（`workers × (pool_size + max_overflow) ≤ max_connections × 70%`）。

    Args:
        settings: 应用配置（worker 数、库目标与按服务的池参数）。

    Returns:
        list[str]: 超限告警文案（空列表表示均在预算内；`max_connections == 0` 跳过）。
    """
    workers = settings.server.workers
    targets = {
        "platform": settings.database.platform,
        "tenants": settings.database.tenants,
        "archive": settings.database.archive,
    }
    warnings: list[str] = []
    for name, target in targets.items():
        if target.max_connections <= 0:
            continue
        pool = target.effective_pool(settings.app.service)
        if not EngineRegistry.check_connection_budget(
            workers=workers,
            pool_size=pool.pool_size,
            max_overflow=pool.max_overflow,
            max_connections=target.max_connections,
        ):
            warnings.append(
                f"{name}: workers={workers} × (pool_size={pool.pool_size} + max_overflow={pool.max_overflow}) "
                f"超出 max_connections={target.max_connections} 的 70% 连接预算"
            )
    return warnings


def tenant_pool_budget_warnings(settings: Settings, max_active: int) -> list[str]:
    """按活跃引擎数核算租户库连接预算（共享租户库口径，启动期告警）。

    口径：`max_active × workers × (pool_size + max_overflow) ≤ tenants.max_connections × 70%`；
    `max_connections == 0` 跳过（不校验）。超限返回 WARNING 文案，不阻断启动。

    Args:
        settings: 应用配置（worker 数、租户库目标与按服务的池参数）。
        max_active: 租户引擎活跃上限（`[tenant].engine_max_active`）。

    Returns:
        list[str]: 超限告警文案（空列表表示在预算内）。
    """
    target = settings.database.tenants
    if target.max_connections <= 0:
        return []
    pool = target.effective_pool(settings.app.service)
    workers = settings.server.workers
    total = max_active * workers * (pool.pool_size + pool.max_overflow)
    if total <= target.max_connections * _CONNECTION_BUDGET_RATIO:
        return []
    return [
        f"tenants: 活跃引擎上限 {max_active} × workers={workers} × "
        f"(pool_size={pool.pool_size} + max_overflow={pool.max_overflow}) = {total} "
        f"超出 max_connections={target.max_connections} 的 70% 连接预算"
    ]
