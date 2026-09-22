"""主库故障只读降级测试（Kiwi 984）：标记 / 探测 / 写被拒 / 恢复 / 异常转译。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.errors import register_exception_handlers
from app.core.config import Settings
from app.db.engine import EngineFactory
from app.db.health import PrimaryHealth
from app.db.registry import EngineRegistry
from app.db.session import SessionFactory, get_write_db

_BAD_SQLITE = "sqlite+aiosqlite:////nonexistent_dir_xyz/bms.db"


async def _probe_false() -> bool:
    """模拟探测失败。"""
    return False


def _memory_settings() -> Settings:
    """SQLite 内存配置。"""
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    settings.database.platform.replicas = []
    return settings


@pytest.mark.kiwi_id(984)
async def test_mark_probe_and_recover() -> None:
    """探测成功清标记；探测失败置标记。"""
    health = PrimaryHealth(EngineFactory(_memory_settings()))
    assert health.is_degraded() is False
    assert await health.probe() is True
    health.mark_degraded()
    assert health.is_degraded() is True
    assert await health.probe() is True
    assert health.is_degraded() is False

    bad_settings = Settings()
    bad_settings.database.platform.url = _BAD_SQLITE
    bad = PrimaryHealth(EngineFactory(bad_settings))
    assert await bad.probe() is False
    assert bad.is_degraded() is True
    await bad.aclose()
    assert bad.is_degraded() is False


async def _build_app(factory: EngineFactory, health: PrimaryHealth) -> FastAPI:
    """构造带主库状态与写依赖的测试应用。"""
    app = FastAPI()
    register_exception_handlers(app)
    app.state.engine_registry = EngineRegistry(factory)
    app.state.session_factory = SessionFactory()
    app.state.primary_health = health

    @app.get("/write")
    async def _write(session: Annotated[AsyncSession, Depends(get_write_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": isinstance(session.bind, AsyncEngine)}

    @app.get("/boom")
    async def _boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise OperationalError("boom", {}, Exception("connection lost"))

    return app


@pytest.mark.kiwi_id(984)
async def test_degraded_write_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """降级态探测失败：写依赖抛 503 / 10006。"""
    factory = EngineFactory(_memory_settings())
    health = PrimaryHealth(factory)
    health.mark_degraded()
    monkeypatch.setattr(health, "probe", _probe_false)
    app = await _build_app(factory, health)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/write")
    assert response.status_code == 503
    assert response.json()["code"] == 10006
    await app.state.engine_registry.aclose()


@pytest.mark.kiwi_id(984)
async def test_degraded_write_recovers() -> None:
    """降级态探测成功：写依赖恢复可用并清标记。"""
    factory = EngineFactory(_memory_settings())
    health = PrimaryHealth(factory)
    health.mark_degraded()
    app = await _build_app(factory, health)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/write")
    assert response.status_code == 200
    assert health.is_degraded() is False
    await app.state.engine_registry.aclose()


@pytest.mark.kiwi_id(984)
async def test_operational_error_translated_and_degraded() -> None:
    """连接类异常 → 503 / 10006 且标记主库降级。"""
    factory = EngineFactory(_memory_settings())
    health = PrimaryHealth(factory)
    app = await _build_app(factory, health)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 503
    assert response.json()["code"] == 10006
    assert health.is_degraded() is True
    await app.state.engine_registry.aclose()
