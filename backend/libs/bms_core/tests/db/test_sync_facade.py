"""达梦同步门面与会话入口分流测试（Kiwi 1155）：方言判定 / 门面行为 / 注册表同步取用。

不连真库：门面行为用同步 SQLite 引擎验证；方言分流只做判定与对象类型断言（建引擎不建连）。
"""

from pathlib import Path
from typing import Annotated, cast

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, String, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import DbSession, SessionFactory, get_db, get_read_db, get_uow, get_write_db, session_scope
from bms_core.db.sync import SyncSession, is_sync_only_url, sync_session_scope
from bms_core.db.unit_of_work import DbUnitOfWork

_DM_URL = "dm+dmPython://SYSDBA:secret@192.0.2.10:5236/BMS_TEST_DM"
"""达梦连接串（不建连；仅用于方言判定与引擎构造）。"""


class _Base(DeclarativeBase):
    """探针模型基类（仅本用例使用，不参与平台模型登记）。"""


class SyncProbe(_Base):
    """同步门面探针表。"""

    __tablename__ = "sync_probe"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(16))


def _settings(url: str) -> Settings:
    """按平台库连接串构造配置。"""
    settings = Settings()
    settings.database.platform.url = url
    settings.database.tenants.url = url
    return settings


def _sync_engine(tmp_path: Path) -> Engine:
    """建同步 SQLite 引擎并建探针表。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}")
    _Base.metadata.create_all(engine)
    return engine


@pytest.mark.kiwi_id(1156)
def test_is_sync_only_url() -> None:
    """方言判定：仅 `dm` 为同步方言；其余方言走异步路径。"""
    assert is_sync_only_url(_DM_URL) is True
    assert is_sync_only_url("mysql+aiomysql://u:p@h:3306/db") is False
    assert is_sync_only_url("postgresql+psycopg://u:p@h:5432/db") is False
    assert is_sync_only_url("sqlite+aiosqlite:///:memory:") is False


@pytest.mark.kiwi_id(1156)
async def test_sync_session_crud_and_scope(tmp_path: Path) -> None:
    """同步门面：写入 / 查询 / 取键 / 刷新 / 删除 / 提交 / 关闭（异常原样上抛）。"""
    engine = _sync_engine(tmp_path)
    try:
        async with sync_session_scope(engine) as session:
            session.add(SyncProbe(id=1, name="demo"))
            await session.flush()
            assert (await session.execute(text("SELECT COUNT(*) FROM sync_probe"))).scalar_one() == 1
            loaded = await session.get(SyncProbe, 1)
            assert loaded is not None
            await session.refresh(loaded)
            assert loaded.name == "demo"
            assert session.get_bind() is engine
            await session.delete(loaded)
            await session.commit()
            await session.rollback()

        async with sync_session_scope(engine) as session:
            assert (await session.execute(text("SELECT COUNT(*) FROM sync_probe"))).scalar_one() == 0

        with pytest.raises(SQLAlchemyError):
            async with sync_session_scope(engine) as session:
                await session.execute(text("SELECT COUNT(*) FROM no_such_table"))

        # 会话上下文协议与逃生口（门面未覆盖能力经 `raw` 取底层阻塞会话）
        async with SyncSession(engine) as session:
            assert isinstance(session.raw, Session)
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(1156)
async def test_sync_session_unit_of_work(tmp_path: Path) -> None:
    """同步门面与 `DbUnitOfWork` 组合：事务边界提交 / 回滚（会话契约放宽后同一工作单元）。"""
    engine = _sync_engine(tmp_path)
    try:
        async with sync_session_scope(engine) as session:
            unit = DbUnitOfWork(session)
            assert unit.session is session
            async with unit.begin():
                session.add(SyncProbe(id=2, name="committed"))

        with pytest.raises(RuntimeError):
            async with sync_session_scope(engine) as session:
                unit = DbUnitOfWork(session)
                async with unit.begin():
                    session.add(SyncProbe(id=3, name="rolled-back"))
                    raise RuntimeError("boom")

        async with sync_session_scope(engine) as session:
            assert await session.get(SyncProbe, 2) is not None
            assert await session.get(SyncProbe, 3) is None
    finally:
        engine.dispose()


@pytest.mark.kiwi_id(1156)
async def test_registry_sync_path_and_dialect_dispatch() -> None:
    """注册表同步取用：`is_sync_only` / `get_sync` 可用；异步 `get` 对同步方言仍失败。

    会话入口按方言分流：达梦目标经同步门面承载（建引擎不建连，故不连真库即可断言）。
    """
    registry = EngineRegistry(EngineFactory(_settings(_DM_URL)))
    try:
        assert registry.is_sync_only(PLATFORM_DB_KEY) is True
        sync_engine = await registry.get_sync(PLATFORM_DB_KEY)
        assert isinstance(sync_engine, Engine)
        assert await registry.get_sync(PLATFORM_DB_KEY) is sync_engine
        with pytest.raises(ConfigError):
            await registry.get(PLATFORM_DB_KEY)

        async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
            assert isinstance(session, SyncSession)

        await registry.get_sync("tenant_demo")
        assert "tenant_demo" in registry.active_keys()
        await registry.release("tenant_demo")
        assert "tenant_demo" not in registry.active_keys()
    finally:
        await registry.aclose()

    async_registry = EngineRegistry(EngineFactory(_settings("sqlite+aiosqlite:///:memory:")))
    try:
        assert async_registry.is_sync_only(PLATFORM_DB_KEY) is False
        async_engine = await async_registry.get(PLATFORM_DB_KEY)
        assert isinstance(async_engine, AsyncEngine)
        async with session_scope(async_registry, db_key=PLATFORM_DB_KEY) as session:
            assert not isinstance(session, SyncSession)
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await async_registry.aclose()


@pytest.mark.kiwi_id(1156)
async def test_request_level_dependencies_use_sync_facade() -> None:
    """请求级会话依赖按方言分流：达梦目标下 `get_db` / 只读 / 写 / 工作单元均得同步门面。"""
    registry = EngineRegistry(EngineFactory(_settings(_DM_URL)))
    app = FastAPI()
    app.state.engine_registry = registry
    app.state.session_factory = SessionFactory()

    @app.get("/db")
    async def db(session: Annotated[DbSession, Depends(get_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"sync": isinstance(session, SyncSession)}

    @app.get("/read")
    async def read(session: Annotated[DbSession, Depends(get_read_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"sync": isinstance(session, SyncSession)}

    @app.get("/write")
    async def write(session: Annotated[DbSession, Depends(get_write_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"sync": isinstance(session, SyncSession)}

    @app.get("/uow")
    async def uow(unit: Annotated[DbUnitOfWork, Depends(get_uow)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        session = cast("DbSession | None", unit.session)
        return {"sync": isinstance(session, SyncSession)}

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/db", "/read", "/write", "/uow"):
                response = await client.get(path)
                assert response.status_code == 200
                assert response.json() == {"sync": True}
    finally:
        await registry.aclose()
