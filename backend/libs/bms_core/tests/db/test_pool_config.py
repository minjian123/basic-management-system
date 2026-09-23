"""连接池按服务与 worker、连接超时与连接预算告警测试（Kiwi 984）。"""

import pytest
import sqlalchemy.ext.asyncio as sa_async

from bms_core.core.config import DbPoolSettings, Settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import pool_budget_rows, pool_budget_warnings


class _FakeEngine:
    """伪异步引擎：仅用于捕获建引擎参数。"""

    async def dispose(self) -> None:
        """空释放。"""


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, object]]]:
    """替换建引擎入口，返回捕获列表。"""
    captured: list[tuple[str, dict[str, object]]] = []

    def _fake_create(url: str, **kwargs: object) -> _FakeEngine:
        captured.append((url, kwargs))
        return _FakeEngine()

    monkeypatch.setattr(sa_async, "create_async_engine", _fake_create)
    return captured


@pytest.mark.kiwi_id(984)
def test_pool_params_and_service_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """池参数取服务覆盖；`connect_args` 按方言传建连超时；分字段密码合成进 URL。"""
    captured = _capture(monkeypatch)
    settings = Settings()
    settings.database.platform.url = "mysql+aiomysql://bms@db:3306/bms_dev"
    settings.database.platform.password = "pw"
    settings.app.service = "svc"
    settings.database.platform.services = {
        "svc": DbPoolSettings(pool_size=9, max_overflow=1, pool_timeout=5.0, pool_recycle=60, connect_timeout=3.0)
    }
    EngineFactory(settings).create("platform")

    url, kwargs = captured[0]
    assert "pw" in url
    assert kwargs["pool_size"] == 9
    assert kwargs["max_overflow"] == 1
    assert kwargs["pool_timeout"] == 5.0
    assert kwargs["pool_recycle"] == 60
    assert kwargs["connect_args"] == {"connect_timeout": 3}


@pytest.mark.kiwi_id(984)
def test_pool_defaults_and_sqlite_no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """无服务覆盖回落默认池；SQLite 不带池参数与建连超时。"""
    captured = _capture(monkeypatch)
    server = Settings()
    server.database.platform.url = "postgresql+psycopg://bms@db:5432/bms_dev"
    EngineFactory(server).create("platform")
    server_kwargs = captured[0][1]
    assert server_kwargs["pool_size"] == 5
    assert server_kwargs["max_overflow"] == 10
    assert server_kwargs["connect_args"] == {"connect_timeout": 10}

    sqlite_settings = Settings()
    sqlite_settings.database.platform.url = "sqlite+aiosqlite:///./app.db"
    EngineFactory(sqlite_settings).create("platform")
    sqlite_kwargs = captured[1][1]
    assert sqlite_kwargs == {"pool_pre_ping": True}


@pytest.mark.kiwi_id(984)
def test_pool_budget_warnings() -> None:
    """连接预算：按服务 × 库类别逐行核算；超限出告警；`max_connections=0` 跳过。"""
    settings = Settings()
    settings.server.workers = 2
    settings.database.platform.max_connections = 10
    settings.database.platform.pool = DbPoolSettings(pool_size=5, max_overflow=10)
    messages = pool_budget_warnings(settings)
    assert any(".platform" in message for message in messages)

    settings.database.platform.max_connections = 0
    assert pool_budget_warnings(settings) == []


@pytest.mark.kiwi_id(984)
def test_pool_budget_rows_service_override() -> None:
    """按服务核算：worker 数与最大连接数均支持按服务覆盖（缺省回落目标级 / 全局）。"""
    settings = Settings()
    settings.server.workers = 2
    settings.server.workers_by_service = {"org": 8}
    settings.database.platform.max_connections_by_service = {"org": 200}
    settings.database.platform.pool = DbPoolSettings(pool_size=5, max_overflow=10)

    rows = {row.name: row for row in pool_budget_rows(settings, services=("org",))}
    org = rows["org.platform"]
    assert org.workers == 8
    assert org.max_connections == 200
    assert org.total == 8 * 15
    assert org.ok is True

    # 未覆盖 `max_connections` 时回落目标级（0 = 不校验 → 视为在预算内）
    settings.database.platform.max_connections = 100
    rows = {row.name: row for row in pool_budget_rows(settings, services=("ai",))}
    ai = rows["ai.platform"]
    assert ai.max_connections == 100
    assert ai.workers == 2
    assert ai.ok is True  # 2 × 15 = 30 ≤ 70

    # 租户库按活跃租户数核算：active × workers × (pool + overflow)
    settings.database.tenants.pool = DbPoolSettings(pool_size=5, max_overflow=10)
    settings.database.tenants.max_connections = 100
    rows = {row.name: row for row in pool_budget_rows(settings, services=("ai",), active_tenants=3)}
    tenants = rows["ai.tenants"]
    assert tenants.total == 3 * 2 * 15
    assert tenants.ok is False  # 90 > 70
    assert "3 活跃租户" in tenants.describe()
