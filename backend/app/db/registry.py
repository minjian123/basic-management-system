"""多租户引擎注册表：`{db_key → AsyncEngine}` 生命周期管理（占位实现）。

- 平台引擎常驻；租户引擎懒加载、LRU 闲置回收（默认 30 分钟）。
- 连接预算校验与并发保护（进程内锁 + Redis SETNX 钩子占位）。
- 真实多实例隔离 / LRU 实测随落库阶段。
"""

import asyncio
import time

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.capability import BaseAsyncResource
from app.db.engine import EngineFactory

PLATFORM_DB_KEY = "platform"
_MAX_ACTIVE_DEFAULT = 32
_IDLE_TIMEOUT_DEFAULT = 1800.0
_CONNECTION_BUDGET_RATIO = 0.7


class EngineRegistry(BaseAsyncResource):
    """异步引擎注册表：平台常驻 + 租户懒加载 + LRU 回收。"""

    def __init__(
        self,
        factory: EngineFactory,
        *,
        max_active: int = _MAX_ACTIVE_DEFAULT,
        idle_timeout: float = _IDLE_TIMEOUT_DEFAULT,
    ) -> None:
        """初始化。

        Args:
            factory: 引擎工厂。
            max_active: 租户引擎活跃上限。
            idle_timeout: 闲置回收阈值（秒）。
        """
        self._factory = factory
        self._max_active = max_active
        self._idle_timeout = idle_timeout
        self._engines: dict[str, AsyncEngine] = {}
        self._last_used: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, db_key: str = PLATFORM_DB_KEY) -> AsyncEngine:
        """取 / 建引擎（平台常驻、租户懒加载）并刷新使用时间。

        Args:
            db_key: 数据源键。

        Returns:
            AsyncEngine: 异步引擎。
        """
        engine = self._engines.get(db_key)
        if engine is not None:
            self._touch(db_key)
            return engine
        async with self._lock_for(db_key):
            engine = self._engines.get(db_key)
            if engine is None:
                await self._evict()
                engine = self._factory.create(db_key)
                self._engines[db_key] = engine
            self._touch(db_key)
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
        """跨实例创建锁的 Redis 键（占位；回补时经 SETNX 使用）。

        Args:
            db_key: 数据源键。

        Returns:
            str: Redis 键。
        """
        return f"bms:global:engine:{db_key}"

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

    async def _evict(self) -> None:
        """回收：先按闲置阈值，再按活跃上限逐出最久未用租户引擎。"""
        now = time.monotonic()
        for db_key in list(self._engines):
            if db_key == PLATFORM_DB_KEY:
                continue
            if now - self._last_used.get(db_key, now) > self._idle_timeout:
                await self._dispose(db_key)
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
