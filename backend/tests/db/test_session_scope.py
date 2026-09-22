"""统一会话入口测试（Kiwi 1050）：库键解析 / 读写角色透传 / 自定义会话工厂。"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.context import reset_tenant_context, set_tenant_context
from app.db.engine import EngineFactory
from app.db.registry import EngineRegistry
from app.db.session import SessionFactory, session_scope
from app.db.tenant import TenantContext

_MEMORY = "sqlite+aiosqlite:///:memory:"


def _settings() -> Settings:
    """构造 SQLite 内存配置（平台库 / 租户库 / 单副本）。"""
    settings = Settings()
    settings.database.platform.url = _MEMORY
    settings.database.platform.replicas = [_MEMORY]
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
    token = set_tenant_context(TenantContext(tenant_code="demo", db_key="tenant_demo", name="演示租户", tenant_id=1))
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
