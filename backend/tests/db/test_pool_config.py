"""连接池按服务与 worker、连接超时与连接预算告警测试（Kiwi 984）。"""

import pytest

import app.db.engine as engine_module
from app.core.config import DbPoolSettings, Settings
from app.db.engine import EngineFactory
from app.db.registry import pool_budget_warnings


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

    monkeypatch.setattr(engine_module, "create_async_engine", _fake_create)
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
    sqlite_settings.database.platform.url = "sqlite+aiosqlite:///./bms_platform.db"
    EngineFactory(sqlite_settings).create("platform")
    sqlite_kwargs = captured[1][1]
    assert sqlite_kwargs == {"pool_pre_ping": True}


@pytest.mark.kiwi_id(984)
def test_pool_budget_warnings() -> None:
    """连接预算：超限出告警；`max_connections=0` 跳过。"""
    settings = Settings()
    settings.server.workers = 2
    settings.database.platform.max_connections = 10
    settings.database.platform.pool = DbPoolSettings(pool_size=5, max_overflow=10)
    messages = pool_budget_warnings(settings)
    assert any("platform" in message for message in messages)

    settings.database.platform.max_connections = 0
    assert pool_budget_warnings(settings) == []
