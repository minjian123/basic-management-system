"""统一会话入口测试（Kiwi 1050）：库键解析 / 读写角色透传 / 自定义会话工厂 / 方言分流。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.context import reset_tenant_context, set_tenant_context
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, get_db, session_scope
from bms_core.db.sync import SyncSession
from bms_core.db.tenant import TenantContext

_MEMORY = "sqlite+aiosqlite:///:memory:"
_DM_URL = "dm+dmPython://user:pass@127.0.0.1:5236/bms"


def _settings() -> Settings:
    """构造 SQLite 内存配置（平台库 / 租户库 / 单副本）。"""
    settings = Settings()
    settings.database.platform.url = _MEMORY
    settings.database.platform.replicas = ConcurrentStableList([_MEMORY])
    settings.database.tenants.url = _MEMORY
    return settings


class RecordingSessionFactory(SessionFactory):
    """记录 `create` 调用的会话工厂（验证自定义工厂生效）。"""

    called: bool = False

    def create(self, options: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """创建会话工厂并打标。

        Args:
            options: 异步引擎。

        Returns:
            async_sessionmaker[AsyncSession]: 会话工厂。
        """
        type(self).called = True
        return super().create(options)


class RecordingRegistry(EngineRegistry):
    """记录只读参数的注册表（验证读写角色透传）。"""

    last_read_only: bool | None = None

    async def get(self, db_key: str = "platform", *, read_only: bool = False) -> AsyncEngine:
        """取引擎并记录只读参数。

        Args:
            db_key: 数据源键。
            read_only: 是否只读。

        Returns:
            AsyncEngine: 异步引擎。
        """
        type(self).last_read_only = read_only
        return await super().get(db_key, read_only=read_only)


@pytest.mark.kiwi_id(1050)
async def test_session_scope_tenant_key_and_custom_factory() -> None:
    """无显式库键时按当前租户上下文库键取引擎；自定义会话工厂生效。"""
    registry = EngineRegistry(EngineFactory(_settings()))
    token = set_tenant_context(TenantContext(code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1))
    RecordingSessionFactory.called = False
    try:
        async with session_scope(registry, factory=RecordingSessionFactory()) as session:
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        reset_tenant_context(token)
    assert RecordingSessionFactory.called is True
    assert "tenant_demo" in registry.active_keys()
    await registry.aclose()


@pytest.mark.kiwi_id(1050)
async def test_session_scope_demo_fallback_explicit_key_and_read_only() -> None:
    """无上下文回落演示租户；显式库键优先；只读角色透传注册表。"""
    registry = RecordingRegistry(EngineFactory(_settings()))
    async with session_scope(registry, db_key="platform") as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    assert "platform" in registry.active_keys()
    assert "tenant_demo" not in registry.active_keys()

    async with session_scope(registry, read_only=True) as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    assert RecordingRegistry.last_read_only is True
    assert "tenant_demo" in registry.active_keys()
    await registry.aclose()


def _dm_settings() -> Settings:
    """构造达梦（同步方言）配置：建引擎不建连，故无需真库。

    Returns:
        Settings: 平台库指向达梦 URL 的配置。
    """
    settings = Settings()
    settings.database.platform.url = _DM_URL
    settings.database.platform.replicas = ConcurrentStableList([_DM_URL])
    return settings


@pytest.mark.kiwi_id(1050)
async def test_session_scope_sync_dialect_uses_sync_facade() -> None:
    """同步方言经同步门面承载（验证方言分流与门的取放在同一入口内完成）。"""
    registry = EngineRegistry(EngineFactory(_dm_settings()))
    try:
        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            assert isinstance(session, SyncSession)
    finally:
        await registry.aclose()


@pytest.mark.kiwi_id(1050)
async def test_request_db_dependency_sync_dialect_uses_sync_facade() -> None:
    """请求级依赖 `get_db` 在同步方言下返回同步门面。"""
    registry = EngineRegistry(EngineFactory(_dm_settings()))
    app = FastAPI()
    app.state.engine_registry = registry
    app.state.session_factory = SessionFactory()

    @app.get("/db")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def db(session: Annotated[DbSession, Depends(get_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"sync": isinstance(session, SyncSession)}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/db")
            assert response.status_code == 200
            assert response.json() == {"sync": True}
    finally:
        await registry.aclose()
