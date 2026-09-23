"""租户源测试（Kiwi 1019）：平台库取数 / 缓存命中与失效 / 未知与停用 / 强制回收。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.config import Settings
from bms_core.core.exceptions import TenantNotFoundError, TenantSuspendedError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_tenant.models.tenant import SysTenant
from bms_tenant.sources.tenant_source import LocalTenantSource


@pytest.fixture
async def platform_url(tmp_path: Path) -> AsyncIterator[str]:
    """临时平台库：建 `sys_tenant` 表并写入 active / suspended / 软删除三类租户。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[cast("Table", SysTenant.__table__)])
    async with factory() as session:
        session.add_all(
            [
                SysTenant(code="demo", name="演示租户", domain="demo.bms.example.com", db_key="tenant_demo"),
                SysTenant(code="acme", name="示例租户", domain="acme.bms.example.com", db_key="tenant_acme"),
                SysTenant(
                    code="sosp",
                    name="停用租户",
                    domain="sosp.bms.example.com",
                    db_key="tenant_sosp",
                    status="suspended",
                ),
            ]
        )
        await session.commit()
        removed = SysTenant(code="gone", name="已删除租户", db_key="tenant_gone")
        removed.soft_delete()
        session.add(removed)
        await session.commit()
    await engine.dispose()
    yield url


def _source(url: str, *, cache: CacheRegion | None = None) -> tuple[LocalTenantSource, EngineRegistry]:
    """构造租户源与引擎注册表（平台库指向临时文件）。"""
    settings = Settings()
    settings.database.platform.url = url
    registry = EngineRegistry(EngineFactory(settings))
    return LocalTenantSource(registry, cache=cache, cache_ttl=60), registry


@pytest.mark.kiwi_id(1019)
async def test_lookup_by_code_and_domain(platform_url: str) -> None:
    """按编码 / 子域名命中注册记录；上下文携带主键 / 状态 / 域名。"""
    source, registry = _source(platform_url)
    try:
        demo = await source.by_code("demo")
        assert demo.tenant_code == "demo"
        assert demo.db_key == "tenant_demo"
        assert demo.name == "演示租户"
        assert demo.tenant_id is not None
        assert demo.status == "active"

        acme = await source.by_domain("acme.bms.example.com")
        assert acme.tenant_code == "acme"
        assert acme.domain == "acme.bms.example.com"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_unknown_and_soft_deleted_rejected(platform_url: str) -> None:
    """未知租户 / 软删除租户：404 / 80001。"""
    source, registry = _source(platform_url)
    try:
        with pytest.raises(TenantNotFoundError) as unknown:
            await source.by_code("nope")
        assert unknown.value.http_status == 404
        assert unknown.value.code == 80001

        with pytest.raises(TenantNotFoundError):
            await source.by_code("gone")
        with pytest.raises(TenantNotFoundError):
            await source.by_domain("nope.bms.example.com")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_suspended_tenant_released_and_rejected(platform_url: str) -> None:
    """停用租户：403 / 80002 且该租户引擎被强制回收。"""
    source, registry = _source(platform_url)
    try:
        assert await registry.get("tenant_sosp") is not None
        assert "tenant_sosp" in registry.active_keys()
        with pytest.raises(TenantSuspendedError) as suspended:
            await source.by_code("sosp")
        assert suspended.value.http_status == 403
        assert suspended.value.code == 80002
        assert "tenant_sosp" not in registry.active_keys()
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_cache_hit_and_invalidate(platform_url: str) -> None:
    """缓存命中减少平台库查询；`invalidate` 后重查。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    try:
        first = await source.by_code("demo")
        assert first.tenant_id is not None

        engine = create_async_engine(platform_url)
        factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            row = await session.get(SysTenant, first.tenant_id)
            assert row is not None
            await session.delete(row)
            await session.commit()
        await engine.dispose()

        cached = await source.by_code("demo")
        assert cached.tenant_id == first.tenant_id

        await source.invalidate(code="demo")
        with pytest.raises(TenantNotFoundError):
            await source.by_code("demo")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_no_cache_direct_query(platform_url: str) -> None:
    """无缓存实现（null / 未装配）时直查平台库，不阻断。"""
    source, registry = _source(platform_url)
    try:
        assert (await source.by_code("acme")).tenant_code == "acme"
        await source.invalidate(code="acme", domain="acme.bms.example.com")
        await source.invalidate()  # 无键失效：空操作
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_invalidate_by_domain(platform_url: str) -> None:
    """按域名单键失效覆盖 `if domain` 分支（缓存实现缺省 null 时空操作）。"""
    source, registry = _source(platform_url)
    try:
        await source.by_code("demo")
        await source.invalidate(domain="demo.bms.example.com")
    finally:
        await registry.aclose()
