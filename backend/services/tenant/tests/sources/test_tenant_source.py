"""租户源测试（Kiwi 1019）：平台库取数 / 缓存命中与失效 / 未知与停用 / 强制回收。"""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.cache.base import CacheRegion
from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.config import Settings
from bms_core.core.exceptions import MultipleActiveTenantsError, TenantNotFoundError, TenantSuspendedError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.tenant_registry import snapshot_cache_key
from bms_core.models.base import Base
from bms_tenant.models.tenant import SysTenant
from bms_tenant.models.tenant_database import SysTenantDatabase
from bms_tenant.sources.tenant_source import LocalTenantSource


@pytest.fixture
async def platform_url(tmp_path: Path) -> AsyncIterator[str]:
    """临时平台库：建 `sys_tenant` + `sys_tenant_database` 表并写入租户（含改名租户）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[cast("Table", SysTenant.__table__), cast("Table", SysTenantDatabase.__table__)],
        )
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
                SysTenant(code="renamed", name="改名租户", domain="renamed.bms.example.com"),
            ]
        )
        await session.flush()
        demo = (await session.execute(select(SysTenant).where(SysTenant.code == "demo"))).scalar_one()
        renamed = (await session.execute(select(SysTenant).where(SysTenant.code == "renamed"))).scalar_one()
        session.add_all(
            [
                SysTenantDatabase(tenant_id=int(demo.id), db_basis="demo"),
                SysTenantDatabase(tenant_id=int(renamed.id), db_basis="orig"),
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
        assert demo.code == "demo"
        assert demo.db_key == "tenant_demo"
        assert demo.name == "演示租户"
        assert demo.tenant_id is not None
        assert demo.status == "active"

        acme = await source.by_domain("acme.bms.example.com")
        assert acme.code == "acme"
        assert acme.domain == "acme.bms.example.com"
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
@pytest.mark.kiwi_id(2219)
async def test_db_basis_from_ledger_keeps_db_key_stable(platform_url: str) -> None:
    """库名基取对照表 `db_basis`：租户改名后库键不变（code 变更不断链）。"""
    source, registry = _source(platform_url)
    try:
        renamed = await source.by_code("renamed")
        assert renamed.code == "renamed"
        assert renamed.db_key == "tenant_orig"

        acme = await source.by_code("acme")  # 无对照行：回落当前 code
        assert acme.db_key == "tenant_acme"
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


async def _soft_delete(url: str, *codes: str) -> None:
    """软删除指定编码的租户行（唯一启用租户解析用例用）。

    Args:
        url: 平台库连接串。
        codes: 待软删除的租户编码。
    """
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for code in codes:
            row = (await session.execute(select(SysTenant).where(SysTenant.code == code))).scalar_one()
            row.soft_delete()
        await session.commit()
    await engine.dispose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_multiple_raises(platform_url: str) -> None:
    """唯一启用租户：≥ 2 个启用租户 → `80004`（不返回清单）。"""
    source, registry = _source(platform_url)
    try:
        with pytest.raises(MultipleActiveTenantsError) as exc:
            await source.single_active()
        assert exc.value.code == 80004 and exc.value.http_status == 409
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_exactly_one(platform_url: str) -> None:
    """唯一启用租户：恰 1 个启用租户 → 其上下文（含库名基 / 主键）；停用 / 软删不计入。"""
    await _soft_delete(platform_url, "acme", "renamed")
    source, registry = _source(platform_url)
    try:
        single = await source.single_active()
        assert single is not None
        assert single.code == "demo" and single.db_key == "tenant_demo" and single.tenant_id is not None
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2239)
async def test_single_active_none(platform_url: str) -> None:
    """唯一启用租户：0 个启用租户 → `None`（沿用既有失败语义由调用方映射）。"""
    await _soft_delete(platform_url, "demo", "acme", "renamed")
    source, registry = _source(platform_url)
    try:
        assert await source.single_active() is None
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
async def test_no_cache_direct_query(platform_url: str) -> None:
    """无缓存实现（null / 未装配）时直查平台库，不阻断。"""
    source, registry = _source(platform_url)
    try:
        assert (await source.by_code("acme")).code == "acme"
        await source.invalidate(code="acme", domain="acme.bms.example.com")
        await source.invalidate()  # 无键失效：空操作
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1019)
@pytest.mark.kiwi_id(2176)
async def test_bump_version_invalidates_cache(platform_url: str) -> None:
    """写路径递增版本号：缓存陈旧重载（内存域经 `bump_version`，Redis 域经域内版本键）。"""
    cache = MemoryCacheRegion(domain="tenant")
    source, registry = _source(platform_url, cache=cache)
    try:
        await source.by_code("demo")
        assert cache.get(snapshot_cache_key("code", "demo")) is not None
        version_before = cache.get_global_version()

        source.bump_version()
        assert cache.get_global_version() == version_before + 1
        await source.by_code("demo")
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(2176)
async def test_invalidate_by_domain(platform_url: str) -> None:
    """按域名单键失效覆盖 `if domain` 分支（缓存实现缺省 null 时空操作）。"""
    source, registry = _source(platform_url)
    try:
        await source.by_code("demo")
        await source.invalidate(domain="demo.bms.example.com")
    finally:
        await registry.aclose()
