"""多租户拓扑路由集成（Kiwi 1019）：真实引擎路由与双租户物理隔离。

- 未配置 `BMS_TEST_DB_URL` 时，三库维度用例跳过（真库连通与隔离实测归 01_05，本文件仅保留守卫）；
- SQLite 真库用例（平台库种子 → 租户库模板 → 引擎路由 → 跨租户隔离）恒常执行；
- 批量迁移固定库清单为纯清单断言（不连库）。
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from bms_core.core.config import Settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_tenant.sources.tenant_source import LocalTenantSource
from ops.seed_tenant import seed_tenants
from ops.test_db import FLOW_STEPS, TEST_DATABASES, main

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(1019)]


@pytest.fixture
def require_test_db_url() -> str:
    """需真库的用例统一前置：未配置 `BMS_TEST_DB_URL` 即跳过。"""
    url = os.environ.get("BMS_TEST_DB_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过三库拓扑集成用例")
    return url


def _settings(tmp_path: Path) -> Settings:
    """临时平台库 + 租户库模板配置。"""
    settings = Settings()
    settings.database.platform.url = f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}"
    settings.database.tenants.url_template = f"sqlite+aiosqlite:///{tmp_path}/bms_tenant_{{tenant}}.db"
    return settings


async def test_platform_engine_is_singleton(tmp_path: Path) -> None:
    """平台引擎常驻：同一 `db_key` 两次取用同一实例。"""
    registry = EngineRegistry(EngineFactory(_settings(tmp_path)))
    try:
        first = await registry.get(PLATFORM_DB_KEY)
        second = await registry.get(PLATFORM_DB_KEY)
        assert first is second
        assert PLATFORM_DB_KEY in registry.active_keys()
    finally:
        await registry.aclose()


async def test_tenant_engine_resolved_by_context(tmp_path: Path) -> None:
    """租户解析 → 库键 → 引擎：demo 上下文取独立租户库引擎（模板解析）。"""
    settings = _settings(tmp_path)
    await seed_tenants(settings.database.platform.url)
    registry = EngineRegistry(EngineFactory(settings))
    try:
        source = LocalTenantSource(registry)
        tenant = await source.by_code("demo")
        assert tenant.db_key == "tenant_demo"
        tenant_engine = await registry.get(tenant.db_key)
        platform_engine = await registry.get(PLATFORM_DB_KEY)
        assert tenant_engine is not platform_engine
        assert str(tenant_engine.url).endswith("bms_tenant_demo.db")
        assert {PLATFORM_DB_KEY, tenant.db_key} <= set(registry.active_keys())
    finally:
        await registry.aclose()


async def test_cross_tenant_isolation_by_db_key(tmp_path: Path) -> None:
    """跨租户物理隔离：写入租户 A 库的数据在租户 B 库不可见。"""
    registry = EngineRegistry(EngineFactory(_settings(tmp_path)))
    try:
        engine_a = await registry.get("tenant_demo")
        engine_b = await registry.get("tenant_acme")
        assert engine_a is not engine_b
        for engine in (engine_a, engine_b):
            async with engine.begin() as connection:
                await connection.execute(text("CREATE TABLE demo_note (id INTEGER PRIMARY KEY, note TEXT)"))
        async with async_sessionmaker(engine_a, expire_on_commit=False)() as session:
            await session.execute(text("INSERT INTO demo_note (id, note) VALUES (1, 'demo')"))
            await session.commit()
        async with async_sessionmaker(engine_b, expire_on_commit=False)() as session:
            assert (await session.execute(text("SELECT note FROM demo_note WHERE id = 1"))).all() == []
    finally:
        await registry.aclose()


async def test_release_and_connection_budget(tmp_path: Path) -> None:
    """租户引擎回收（平台键不回收）与连接预算边界。"""
    registry = EngineRegistry(EngineFactory(_settings(tmp_path)))
    try:
        await registry.get("tenant_demo")
        await registry.release("tenant_demo")
        assert "tenant_demo" not in registry.active_keys()
        await registry.get(PLATFORM_DB_KEY)
        await registry.release(PLATFORM_DB_KEY)
        assert PLATFORM_DB_KEY in registry.active_keys()
    finally:
        await registry.aclose()

    assert EngineRegistry.check_connection_budget(workers=4, pool_size=10, max_overflow=5, max_connections=100) is True
    assert (
        EngineRegistry.check_connection_budget(workers=8, pool_size=20, max_overflow=10, max_connections=100) is False
    )


async def test_env_guarded_engine_routing(require_test_db_url: str) -> None:
    """env 守卫：三库环境按真实 URL 建平台 / 租户引擎（不建连）；真库连通归 01_05。"""
    settings = Settings()
    settings.database.platform.url = require_test_db_url
    settings.database.tenants.url_template = ""
    registry = EngineRegistry(EngineFactory(settings))
    try:
        platform = await registry.get(PLATFORM_DB_KEY)
        tenant = await registry.get("tenant_demo")
        assert str(platform.url) == require_test_db_url
        assert str(tenant.url) == settings.database.tenants.url
    finally:
        await registry.aclose()


def test_test_db_plan_lists_fixed_databases(capsys: pytest.CaptureFixture[str]) -> None:
    """三库测试库流程计划：平台 / 租户两对象与步骤（纯清单断言，无需真库，恒常绿）。"""
    for engine, objects in TEST_DATABASES.items():
        capsys.readouterr()
        assert main(["plan", "--engine", engine]) == 0
        out = capsys.readouterr().out
        for database in objects.values():
            assert database in out
        for step in FLOW_STEPS:
            assert step in out
