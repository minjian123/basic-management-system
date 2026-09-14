"""多租户拓扑路由集成骨架（标记 integration；需 `BMS_TEST_DB_URL`，随首个落库阶段执行）。

骨架口径（见《项目骨架 · 04_02 详细设计》§6.1）：
- 未配置 `BMS_TEST_DB_URL` 时跳过（形态对齐既有 Redis 集成用例），不阻塞冒烟层；
- 占位期对**占位实现**断言（引擎同一性 / 库键分离 / 固定库清单）；
- 真库阶段替换为真实连接与跨租户数据隔离断言，并按方言命名或加方言标记，
  保证 `.gitlab-ci.yml` 的 `pytest -k "$DB_DIALECT"` 有匹配用例（激活前置第 4 项）。
"""

import os

import pytest

from app.core.config import get_settings
from app.db.engine import EngineFactory
from app.db.registry import PLATFORM_DB_KEY, EngineRegistry
from app.db.tenant import DEMO_TENANT, resolve_tenant
from ops.migrate_tenants import resolve_databases
from ops.test_db import FLOW_STEPS, TEST_DATABASES, main

pytestmark = pytest.mark.integration


@pytest.fixture
def require_test_db_url() -> str:
    """需真库的用例统一前置：未配置 `BMS_TEST_DB_URL` 即跳过。"""
    url = os.environ.get("BMS_TEST_DB_URL")
    if not url:
        pytest.skip("未配置 BMS_TEST_DB_URL，跳过三库拓扑集成用例")
    return url


async def test_platform_engine_is_singleton(require_test_db_url: str) -> None:
    """平台引擎常驻：同一 `db_key` 两次取用同一实例。"""
    assert require_test_db_url
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        first = await registry.get(PLATFORM_DB_KEY)
        second = await registry.get(PLATFORM_DB_KEY)
        assert first is second
        assert PLATFORM_DB_KEY in registry.active_keys()
    finally:
        await registry.aclose()


async def test_tenant_engine_resolved_by_context(require_test_db_url: str) -> None:
    """租户解析 → 库键 → 引擎：demo 上下文取 `tenant_demo` 引擎。"""
    assert require_test_db_url
    tenant = resolve_tenant(header="demo")
    assert tenant == DEMO_TENANT
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        tenant_engine = await registry.get(tenant.db_key)
        platform_engine = await registry.get(PLATFORM_DB_KEY)
        assert tenant_engine is not platform_engine
        assert {PLATFORM_DB_KEY, tenant.db_key} <= set(registry.active_keys())
    finally:
        await registry.aclose()


async def test_cross_tenant_isolation_by_db_key(require_test_db_url: str) -> None:
    """跨租户隔离（占位口径）：不同库键取到不同引擎实例，互不共享。

    真库阶段替换为「写入租户 A 表 → 租户 B 查不到」的数据级隔离断言。
    """
    assert require_test_db_url
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        engine_a = await registry.get("tenant_demo")
        engine_b = await registry.get("tenant_other")
        assert engine_a is not engine_b
    finally:
        await registry.aclose()


async def test_release_and_connection_budget(require_test_db_url: str) -> None:
    """租户引擎回收（平台键不回收）与连接预算边界。"""
    assert require_test_db_url
    registry = EngineRegistry(EngineFactory(get_settings()))
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


def test_batch_migration_and_test_db_list(capsys: pytest.CaptureFixture[str]) -> None:
    """批量迁移固定库清单与测试库流程计划（纯清单断言，无需真库，恒常绿）。"""
    assert resolve_databases("all") == ["bms_platform", "bms_tenant_demo", "bms_archive"]
    for engine, database in TEST_DATABASES.items():
        capsys.readouterr()
        assert main(["plan", "--engine", engine]) == 0
        out = capsys.readouterr().out
        assert database in out
        for step in FLOW_STEPS:
            assert step in out
