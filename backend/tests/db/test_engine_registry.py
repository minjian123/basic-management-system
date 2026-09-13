"""多租户引擎注册表测试（Kiwi 27）：常驻 / 懒加载 / LRU / 预算 / 释放。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engine import EngineFactory
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry


def _factory() -> EngineFactory:
    """构造 SQLite 内存引擎工厂。"""
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    settings.database.tenants.url = "sqlite+aiosqlite:///:memory:"
    return EngineFactory(settings)


@pytest.mark.kiwi_id(27)
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


@pytest.mark.kiwi_id(27)
async def test_lru_and_idle_eviction() -> None:
    """活跃上限 LRU 逐出；闲置阈值回收。"""
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


@pytest.mark.kiwi_id(27)
async def test_release_and_lock_reuse() -> None:
    """释放可回收；平台不可回收；创建锁可复用。"""
    registry = EngineRegistry(_factory())
    await registry.get("tenant_a")
    await registry.release("tenant_a")
    assert "tenant_a" not in registry.active_keys()
    await registry.get("tenant_a")
    await registry.release(PLATFORM_DB_KEY)
    assert PLATFORM_DB_KEY not in registry.active_keys()
    assert registry.redis_lock_key("tenant_a") == "bms:global:engine:tenant_a"
    await registry.aclose()


@pytest.mark.kiwi_id(27)
def test_connection_budget() -> None:
    """连接预算：`workers × (pool + overflow) ≤ max_connections × 70%`。"""
    assert EngineRegistry.check_connection_budget(
        workers=2, pool_size=5, max_overflow=10, max_connections=100
    ) is True
    assert EngineRegistry.check_connection_budget(
        workers=10, pool_size=5, max_overflow=10, max_connections=100
    ) is False
