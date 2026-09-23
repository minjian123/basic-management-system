"""多租户引擎注册表：`{db_key → AsyncEngine}` 生命周期管理。

- 平台引擎常驻；**服务租户库引擎**懒加载、LRU 闲置回收（默认 30 分钟；每次访问先清扫）。
- 读写角色：写路径返回主引擎；`read_only=True` 经工厂取副本（轮询 / 回退主），
  注册表仍按 `db_key` 跟踪使用时间与逐出（一次释放该库主 + 副本引擎）。
- 并发保护：创建窗口「进程内 `asyncio.Lock` + 跨实例分布式锁」双重互斥（锁经分布式锁
  能力域，缺省 null 实现不连 Redis）；创建失败快速失败。
- 连接预算：`pool_budget_rows`（**按服务 × 库类别**核算内核）+ `pool_budget_warnings` /
  `tenant_pool_budget_warnings`（启动期告警；离线核对见 `ops/check_budget.py`）。
- 同步方言（达梦）：`get_sync` 提供同步引擎取用，与异步路径同一套清扫 / 记账 / 逐出口径，
  引擎本体由工厂按 `(db_key, 读写角色)` 缓存（详见《后端基类清单》）。
"""

import asyncio
import time
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from sqlalchemy import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseAsyncResource
from bms_core.core.config import Settings
from bms_core.db.engine import EngineFactory
from bms_core.db.inventory import db_counts_by_kind
from bms_core.db.keys import DB_KIND_TENANT, PLATFORM_DB_KEY, parse_db_key
from bms_core.db.sync import is_sync_only_url
from bms_core.lock.base import DEFAULT_LOCK_TTL, BaseDistributedLock, build_lock_key
from bms_core.metrics.base import BaseMetrics
from bms_core.services.module_registry import enabled_service_keys

_MAX_ACTIVE_DEFAULT = 32
_IDLE_TIMEOUT_DEFAULT = 1800.0
_CONNECTION_BUDGET_RATIO = 0.7


def _db_kind(db_key: str) -> str | None:
    """取数据源键的库类别（非法键回落 None，不抛错）。

    Args:
        db_key: 数据源键。

    Returns:
        str | None: 库类别（`platform` / `tenant` / `archive`）；非法键 None。
    """
    try:
        return parse_db_key(db_key).kind
    except Exception:  # 记账路径不因历史键形态失败
        return None


class EngineRegistry(BaseAsyncResource):
    """异步引擎注册表：平台常驻 + 租户懒加载 + LRU 回收 + 跨实例创建锁。"""

    def __init__(
        self,
        factory: EngineFactory,
        *,
        max_active: int = _MAX_ACTIVE_DEFAULT,
        idle_timeout: float = _IDLE_TIMEOUT_DEFAULT,
        lock: BaseDistributedLock | None = None,
        metrics: BaseMetrics | None = None,
        metrics_service: str = "",
    ) -> None:
        """初始化。

        Args:
            factory: 引擎工厂。
            max_active: 租户引擎活跃上限。
            idle_timeout: 闲置回收阈值（秒）。
            lock: 跨实例分布式锁（None 表示仅进程内锁）。
            metrics: 指标记录器（None 表示不记录库数量指标；见 `db/inventory.py`）。
            metrics_service: 指标 `service` 标签取值。
        """
        self._factory = factory
        self._max_active = max_active
        self._idle_timeout = idle_timeout
        self._lock = lock
        self._metrics = metrics
        self._metrics_service = metrics_service
        self._engines: dict[str, AsyncEngine] = {}
        self._sync_keys: set[str] = set()
        self._last_used: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def db_counts(self) -> dict[str, int]:
        """按库类别统计活跃引擎数（运行期库数量水位）。

        Returns:
            dict[str, int]: 库类别 → 活跃数。
        """
        return db_counts_by_kind(self.active_keys())

    async def record_db_counts(self) -> None:
        """记录 `bms_db_count` 指标（按库类别；未装配指标器时为空操作）。

        Returns:
            None: 无返回值。
        """
        if self._metrics is None:
            return
        for kind, count in self.db_counts().items():
            await self._metrics.gauge(
                "bms_db_count", value=float(count), labels={"kind": kind, "service": self._metrics_service}
            )

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
            DataOwnershipError: 全限定键越界且未开启运维豁免（10008）。
            ConfigError: 键形态非法或全限定键服务标识未登记。
        """
        self._factory.validate_key(db_key)
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
        await self.record_db_counts()
        if read_only:
            return self._factory.create(db_key, read_only=True)
        return engine

    def is_sync_only(self, db_key: str = PLATFORM_DB_KEY) -> bool:
        """该数据源是否仅同步方言（不建连，按连接串判定）。

        Args:
            db_key: 数据源键。

        Returns:
            bool: 仅同步方言（达梦）True。

        Raises:
            DataOwnershipError: 全限定键越界且未开启运维豁免（10008）。
            ConfigError: 键形态非法或全限定键服务标识未登记。
        """
        self._factory.validate_key(db_key)
        return is_sync_only_url(self._factory.resolve_url(db_key))

    async def get_sync(self, db_key: str = PLATFORM_DB_KEY, *, read_only: bool = False) -> Engine:
        """取 / 建同步引擎（达梦运行期路径）。

        与 `get` 同一套记账口径：访问先清扫闲置租户引擎、租户键按活跃上限 LRU 逐出；
        同步引擎本体由工厂缓存（键含读写角色），释放统一经 `factory.drop(db_key)`。

        Args:
            db_key: 数据源键。
            read_only: 是否只读（True 时经工厂副本路由）。

        Returns:
            Engine: 同步引擎（不建连）。

        Raises:
            DataOwnershipError: 全限定键越界且未开启运维豁免（10008）。
            ConfigError: 键形态非法或全限定键服务标识未登记。
        """
        self._factory.validate_key(db_key)
        await self._sweep_idle()
        self._touch(db_key)
        if _db_kind(db_key) == DB_KIND_TENANT:
            self._sync_keys.add(db_key)
        await self._evict()
        return self._factory.create_sync(db_key, read_only=read_only)

    async def release(self, db_key: str) -> None:
        """强制回收指定引擎（如租户停用）。

        Args:
            db_key: 数据源键（平台类键不参与强制回收）。
        """
        if _db_kind(db_key) != DB_KIND_TENANT:
            return
        await self._dispose(db_key)
        await self.record_db_counts()

    def active_keys(self) -> list[str]:
        """当前活跃 `db_key` 列表（含平台；异步与同步路径合并视图）。

        Returns:
            list[str]: 数据源键列表。
        """
        return list(dict.fromkeys([*self._engines, *sorted(self._sync_keys)]))

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
        self._sync_keys.clear()
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
        for db_key in self._tenant_keys():
            if now - self._last_used.get(db_key, now) > self._idle_timeout:
                await self._dispose(db_key)

    async def _evict(self) -> None:
        """按活跃上限逐出最久未用租户引擎（创建窗口内调用）。"""
        tenants = self._tenant_keys()
        while len(tenants) >= self._max_active:
            oldest = min(tenants, key=lambda key: self._last_used.get(key, 0.0))
            await self._dispose(oldest)
            tenants.remove(oldest)

    def _tenant_keys(self) -> list[str]:
        """当前活跃服务租户库键（异步与同步路径合并，已排序快照）。

        只统计**库类别为租户**的键：平台类键（含运维跨服务取到的 `platform_{service}`）常驻，
        不参与 LRU 逐出与闲置回收。
        """
        keys = {key for key in self._engines if _db_kind(key) == DB_KIND_TENANT}
        keys |= {key for key in self._sync_keys if _db_kind(key) == DB_KIND_TENANT}
        return sorted(keys)

    async def _dispose(self, db_key: str) -> None:
        """释放并移除单个引擎（异步 + 同步）。"""
        self._last_used.pop(db_key, None)
        await self._factory.drop(db_key)
        self._engines.pop(db_key, None)
        self._sync_keys.discard(db_key)


@dataclass(frozen=True)
class PoolBudgetRow(BaseObject):
    """连接预算核算行（服务 × 库类别；启动告警与离线核对的统一载体）。"""

    name: str
    """展示名（`{service}.{datasource}`；归档库为 `archive`）。"""

    service: str
    """归属服务标识（归档库为空串——归档库不服务化）。"""

    datasource: str
    """库类别（`platform` / `tenants` / `archive`）。"""

    workers: int
    """该服务生效 worker 数（`[server].workers_by_service` 覆盖，缺省回落 `workers`）。"""

    active_tenants: int
    """按活跃租户数核算时的租户数（`0` = 不按活跃数核算）。"""

    pool_size: int
    """该服务生效连接池大小。"""

    max_overflow: int
    """该服务生效溢出连接数。"""

    max_connections: int
    """该服务库最大连接数（`0` = 不校验）。"""

    total: int
    """预计占用连接数（平台 / 归档 = `workers × (pool + overflow)`；租户 = 再乘活跃租户数）。"""

    @property
    def limit(self) -> float:
        """预算上限（`max_connections × 70%`；`max_connections == 0` 时为 0 = 不校验）。

        Returns:
            float: 预算上限。
        """
        return self.max_connections * _CONNECTION_BUDGET_RATIO

    @property
    def ok(self) -> bool:
        """是否在预算内（`max_connections == 0` 视为不校验）。

        Returns:
            bool: 在预算内 True。
        """
        return self.max_connections == 0 or float(self.total) <= self.limit

    def describe(self) -> str:
        """超限告警文案（含服务、库类别与算式）。

        Returns:
            str: 告警文案。
        """
        units = f"{self.active_tenants} 活跃租户 × " if self.active_tenants else ""
        return (
            f"{self.name}: {units}workers={self.workers} × "
            f"(pool_size={self.pool_size} + max_overflow={self.max_overflow}) = {self.total} "
            f"超出 max_connections={self.max_connections} 的 70% 连接预算"
        )


def _budget_row(
    settings: Settings,
    *,
    service: str,
    datasource: str,
    target: object,
    active_tenants: int = 0,
) -> PoolBudgetRow:
    """构造单行连接预算核算（服务覆盖优先，缺省回落目标级 / 全局）。

    Args:
        settings: 应用配置。
        service: 服务标识（归档库传空串）。
        datasource: 库类别。
        target: 数据库目标配置（`DatabaseTargetSettings`）。
        active_tenants: 活跃租户数（仅租户库传；`0` 表示不按活跃数核算）。

    Returns:
        PoolBudgetRow: 核算行。
    """
    from bms_core.core.config import DatabaseTargetSettings  # 局部导入避免配置层与数据层循环

    resolved_target = cast("DatabaseTargetSettings", target)
    effective_service = service or settings.app.service
    pool = resolved_target.effective_pool(effective_service)
    workers = settings.server.workers_for(effective_service)
    units = active_tenants if active_tenants else 1
    total = units * workers * (pool.pool_size + pool.max_overflow)
    return PoolBudgetRow(
        name=f"{service}.{datasource}" if service else datasource,
        service=service,
        datasource=datasource,
        workers=workers,
        active_tenants=active_tenants,
        pool_size=pool.pool_size,
        max_overflow=pool.max_overflow,
        max_connections=resolved_target.max_connections_for(effective_service),
        total=total,
    )


def pool_budget_rows(
    settings: Settings,
    *,
    services: Sequence[str] | None = None,
    active_tenants: int = 0,
) -> list[PoolBudgetRow]:
    """按「服务 × 库类别」核算连接预算（启动告警与离线核对共用同一内核）。

    口径：`workers_for(service) × (pool_size + max_overflow) ≤ max_connections_for(service) × 70%`；
    租户库另按活跃租户数核算（`active_tenants × workers × (pool + overflow)`）。

    Args:
        settings: 应用配置。
        services: 服务标识集合；None 取服务目录**已启用服务**。
        active_tenants: 活跃租户数（`0` = 不按活跃数核算；租户库行专用）。

    Returns:
        list[PoolBudgetRow]: 核算行（保序：平台服务库 → 服务租户库 → 归档库）。
    """
    resolved = tuple(services) if services is not None else enabled_service_keys()
    rows: list[PoolBudgetRow] = []
    for service in resolved:
        rows.append(_budget_row(settings, service=service, datasource="platform", target=settings.database.platform))
    for service in resolved:
        rows.append(
            _budget_row(
                settings,
                service=service,
                datasource="tenants",
                target=settings.database.tenants,
                active_tenants=active_tenants,
            )
        )
    rows.append(_budget_row(settings, service="", datasource="archive", target=settings.database.archive))
    return rows


def pool_budget_warnings(settings: Settings) -> list[str]:
    """计算各「服务 × 库类别」连接预算告警（启动期调用；超限不阻断启动）。

    Args:
        settings: 应用配置（worker 数、库目标与按服务的池参数）。

    Returns:
        list[str]: 超限告警文案（空列表表示均在预算内；`max_connections == 0` 跳过）。
    """
    return [row.describe() for row in pool_budget_rows(settings) if not row.ok]


def tenant_pool_budget_warnings(settings: Settings, max_active: int) -> list[str]:
    """按活跃引擎数核算各服务租户库连接预算（启动期告警）。

    口径：`max_active × workers_for(service) × (pool_size + max_overflow) ≤ max_connections_for(service) × 70%`；
    `max_connections == 0` 跳过（不校验）。超限返回 WARNING 文案，不阻断启动。

    Args:
        settings: 应用配置（worker 数、租户库目标与按服务的池参数）。
        max_active: 租户引擎活跃上限（`[tenant].engine_max_active`）。

    Returns:
        list[str]: 超限告警文案（空列表表示在预算内）。
    """
    rows = pool_budget_rows(settings, active_tenants=max_active)
    return [row.describe() for row in rows if row.datasource == "tenants" and not row.ok]
