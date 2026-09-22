"""多租户引擎注册表测试（Kiwi 1019）：常驻 / 懒加载 / LRU / 闲置清扫 / 跨实例锁 / 预算。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import EngineFactory
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry, tenant_pool_budget_warnings
from app.lock.base import DEFAULT_LOCK_TTL, DEFAULT_WAIT, BaseDistributedLock


def _factory() -> EngineFactory:
    """构造 SQLite 内存引擎工厂。"""
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    settings.database.tenants.url = "sqlite+aiosqlite:///:memory:"
    return EngineFactory(settings)


class _RecordingLock(BaseDistributedLock):
    """记账分布式锁替身（记录 acquire / release 调用；不声明实现名，不入插件登记）。"""

    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.released: list[str] = []

    async def acquire(self, key: str, *, ttl: int = DEFAULT_LOCK_TTL, wait: float = DEFAULT_WAIT) -> str | None:
        """记录获取并恒定成功。"""
        self.acquired.append(key)
        return "token"

    async def release(self, key: str, token: str) -> bool:
        """记录释放并恒定成功。"""
        self.released.append(key)
        return True

    async def extend(self, key: str, token: str, *, ttl: int = DEFAULT_LOCK_TTL) -> bool:
        """恒定续租成功。"""
        return True


@pytest.mark.kiwi_id(1019)
async def test_platform_resident_and_tenant_lazy() -> None:
    """平台常驻（缓存复用）；租户懒加载。"""
    registry = EngineRegistry(_factory())
    platform = await registry.get()
    assert isinstance(platform, AsyncEngine)
    assert await registry.get(PLATFORM_DB_KEY) is platform
    assert isinstance(await registry.get("tenant_a"), AsyncEngine)
    assert set(registry.active_keys()) == {PLATFORM_DB_KEY, "tenant_a"}
    await registry.aclose()
    assert registry.active_keys() == []


@pytest.mark.kiwi_id(1019)
async def test_lru_and_idle_eviction() -> None:
    """活跃上限 LRU 逐出；闲置阈值访问清扫回收；平台引擎不逐出。"""
    registry = EngineRegistry(_factory(), max_active=1)
    await registry.get("tenant_a")
    await registry.get("tenant_b")
    assert registry.active_keys() == ["tenant_b"]

    idle = EngineRegistry(_factory(), idle_timeout=0.0)
    await idle.get("tenant_a")
    await idle.get("tenant_b")
    assert idle.active_keys() == ["tenant_b"]
    await registry.aclose()
    await idle.aclose()


@pytest.mark.kiwi_id(1019)
async def test_release_and_lock_reuse() -> None:
    """释放可回收；平台不可回收；创建锁可复用；锁键符合锁基座规范。"""
    registry = EngineRegistry(_factory())
    await registry.get("tenant_a")
    await registry.release("tenant_a")
    assert "tenant_a" not in registry.active_keys()
    await registry.get("tenant_a")
    await registry.release(PLATFORM_DB_KEY)
    assert PLATFORM_DB_KEY not in registry.active_keys()
    assert registry.redis_lock_key("tenant_a") == "bms:global:lock:engine:tenant_a"
    await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_cross_instance_lock_used_on_creation() -> None:
    """引擎创建窗口经跨实例锁（分布式锁基座）；锁键按库键构造。"""
    lock = _RecordingLock()
    registry = EngineRegistry(_factory(), lock=lock)
    platform = await registry.get(PLATFORM_DB_KEY)
    assert await registry.get(PLATFORM_DB_KEY) is platform
    await registry.get("tenant_a")
    assert lock.acquired == ["bms:global:lock:engine:platform", "bms:global:lock:engine:tenant_a"]
    assert lock.released == lock.acquired
    await registry.aclose()


@pytest.mark.kiwi_id(1019)
def test_connection_budget() -> None:
    """连接预算：`workers × (pool + overflow) ≤ max_connections × 70%`。"""
    assert EngineRegistry.check_connection_budget(workers=2, pool_size=5, max_overflow=10, max_connections=100) is True
    assert (
        EngineRegistry.check_connection_budget(workers=10, pool_size=5, max_overflow=10, max_connections=100) is False
    )


@pytest.mark.kiwi_id(1019)
def test_tenant_pool_budget_warnings() -> None:
    """按活跃引擎数核算租户库连接预算：超限告警；`max_connections=0` 跳过。"""
    settings = Settings()
    settings.server.workers = 2
    settings.database.tenants.pool.pool_size = 5
    settings.database.tenants.pool.max_overflow = 10
    settings.database.tenants.max_connections = 100

    assert tenant_pool_budget_warnings(settings, max_active=2) == []  # 2×2×15 = 60 ≤ 70
    warnings = tenant_pool_budget_warnings(settings, max_active=3)  # 3×2×15 = 90 > 70
    assert len(warnings) == 1
    assert "活跃引擎上限 3" in warnings[0]

    settings.database.tenants.max_connections = 0
    assert tenant_pool_budget_warnings(settings, max_active=100) == []
