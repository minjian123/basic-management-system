"""主库故障只读降级测试（Kiwi 984）：标记 / 探测 / 写被拒 / 恢复 / 异常转译。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.api.errors import register_exception_handlers
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.contention import RETRY_AFTER_SECONDS, contention_driver, is_lock_contention
from bms_core.db.engine import EngineFactory
from bms_core.db.health import PrimaryHealth
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory, get_write_db

pytestmark = pytest.mark.own_db("被测对象是主库故障只读降级：需能把库置成不可写状态")

_BAD_SQLITE = "sqlite+aiosqlite:////nonexistent_dir_xyz/bms.db"


async def _probe_false(db_key: str = "platform") -> bool:
    """模拟探测失败（库键参数随会话租户路由）。"""
    del db_key
    return False


def _memory_settings() -> Settings:
    """SQLite 内存配置。"""
    settings = Settings()
    settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    settings.database.platform.replicas = ConcurrentStableList([])
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
    # bare-collections:allow（FastAPI 端点返回注解）
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


@pytest.mark.kiwi_id(984)
async def test_operational_error_without_primary_health_state() -> None:
    """连接类异常且未装配主库状态：仍转 503 / 10006（跳过降级标记分支）。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def _boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise OperationalError("boom", {}, Exception("connection lost"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 503
    assert response.json()["code"] == 10006


async def _build_contention_app(factory: EngineFactory, health: PrimaryHealth) -> FastAPI:
    """构造「锁争用」与「真故障」两条异常路径的应用（17_01）。

    Args:
        factory: 引擎工厂。
        health: 主库健康态。

    Returns:
        FastAPI: 测试应用（`/lock` 抛争用、`/boom` 抛连接类失败、`/write` 为写依赖）。
    """
    app = FastAPI()
    register_exception_handlers(app)
    app.state.engine_registry = EngineRegistry(factory)
    app.state.session_factory = SessionFactory()
    app.state.primary_health = health

    @app.get("/lock")
    async def _lock() -> None:  # pyright: ignore[reportUnusedFunction]
        raise OperationalError("stmt", {}, Exception("database is locked"))

    @app.get("/boom")
    async def _boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise OperationalError("boom", {}, Exception("connection lost"))

    @app.get("/write")
    # bare-collections:allow（FastAPI 端点返回注解）
    async def _write(session: Annotated[AsyncSession, Depends(get_write_db)]) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": isinstance(session.bind, AsyncEngine)}

    return app


@pytest.mark.kiwi_id(2406)
async def test_lock_contention_not_degraded_and_retryable() -> None:
    """锁争用：503 + 10006 + `Retry-After`，且**不**置只读降级、后续写不被拒。"""
    factory = EngineFactory(_memory_settings())
    health = PrimaryHealth(factory)
    app = await _build_contention_app(factory, health)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/lock")
        assert response.status_code == 503
        assert response.json()["code"] == 10006
        assert response.headers["Retry-After"] == str(RETRY_AFTER_SECONDS)
        assert "繁忙" in response.json()["message"]
        assert health.is_degraded() is False

        # 争用不得把进程打成只读：后续写请求照常
        follow_up = await client.get("/write")
        assert follow_up.status_code == 200

    await app.state.engine_registry.aclose()


@pytest.mark.kiwi_id(2406)
async def test_true_fault_still_degraded_without_retry_after() -> None:
    """真故障：仍置降级且**不带** `Retry-After`（与改动前语义一致）。"""
    factory = EngineFactory(_memory_settings())
    health = PrimaryHealth(factory)
    app = await _build_contention_app(factory, health)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")
        assert response.status_code == 503
        assert response.json()["code"] == 10006
        assert "Retry-After" not in response.headers
        assert health.is_degraded() is True

    await app.state.engine_registry.aclose()


class _MySQLDriverError(Exception):
    """模拟 pymysql 异常：`args[0]` 为错误码（真实驱动据此判定 1205 / 1213）。"""


@pytest.mark.kiwi_id(2406)
def test_contention_driver_markers() -> None:
    """各方言标记识别为真；普通连接类错误识别为假（含 `orig` 包装与 MySQL 错误码）。"""
    assert contention_driver(OperationalError("s", {}, Exception("database is locked"))) == "sqlite"
    assert contention_driver(OperationalError("s", {}, Exception("database table is locked"))) == "sqlite"
    assert (
        contention_driver(OperationalError("s", {}, Exception("Lock wait timeout exceeded; try restarting"))) == "mysql"
    )
    assert contention_driver(OperationalError("s", {}, Exception("Deadlock found when trying to get lock"))) == "mysql"
    assert contention_driver(OperationalError("s", {}, Exception("deadlock detected"))) == "postgresql"
    assert contention_driver(OperationalError("s", {}, Exception("could not obtain lock on row"))) == "postgresql"
    # MySQL 错误码兜底（文本被本地化时仍可识别；`orig.args[0]` 才是错误码）
    assert contention_driver(OperationalError("s", {}, _MySQLDriverError(1205, "锁等待超时"))) == "mysql"
    assert contention_driver(OperationalError("s", {}, _MySQLDriverError(1213, "死锁"))) == "mysql"

    assert contention_driver(OperationalError("s", {}, Exception("connection refused"))) is None
    assert contention_driver(OperationalError("s", {}, _MySQLDriverError(1146, "Table doesn't exist"))) is None
    # 驱动异常没有参数（`args` 为空）时不得取码，按文本判定
    assert contention_driver(OperationalError("s", {}, _MySQLDriverError())) is None
    assert is_lock_contention(RuntimeError("no db here")) is False
