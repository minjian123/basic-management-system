"""服务启动入口测试：配置驱动 uvicorn 与信号优先摘流（Kiwi 1205）。"""

import signal
from typing import cast

import pytest
from fastapi import FastAPI

from bms_core.core import run as run_module
from bms_core.core.config import Settings
from bms_core.core.factory import BaseApplicationFactory
from bms_core.core.run import ServiceServer, build_server
from bms_core.core.service import ServiceIdentity, ServiceRuntime


@pytest.mark.kiwi_id(1205)
def test_build_server_uses_configured_host_port() -> None:
    """启动配置取 `[server]` 的 host / port。"""
    settings = Settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = 9999
    server = build_server(settings, FastAPI())
    assert isinstance(server, ServiceServer)
    assert server.config.host == "127.0.0.1"
    assert server.config.port == 9999


@pytest.mark.kiwi_id(1205)
def test_handle_exit_drains_then_stops() -> None:
    """信号处理：先摘流（draining）再置退出标志（should_exit）。"""
    app = FastAPI()
    app.state.startup_complete = True
    runtime = ServiceRuntime(app, ServiceIdentity(name="platform", version="0.1.0"))
    server = build_server(Settings(), app, on_drain=runtime)
    server.handle_exit(signal.SIGTERM, None)
    assert runtime.draining is True
    assert app.state.startup_complete is False
    assert server.should_exit is True


@pytest.mark.kiwi_id(1205)
def test_handle_exit_without_runtime_only_stops() -> None:
    """未接入运行时：仅置退出标志，不抛错。"""
    server = build_server(Settings(), FastAPI())
    server.handle_exit(signal.SIGTERM, None)
    assert server.should_exit is True


@pytest.mark.kiwi_id(1205)
def test_run_service_builds_server_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动主流程：构造应用 → 取停机回调 → 启动服务器（服务器 run 被调用）。"""
    app = FastAPI()
    app.state.startup_complete = True
    runtime = ServiceRuntime(app, ServiceIdentity(name="platform", version="0.1.0"))

    class _Factory(BaseApplicationFactory):
        def create(self, options: None = None) -> FastAPI:
            return app

    captured: dict[str, object] = {}

    class _Server:
        def run(self) -> None:
            captured["ran"] = True

    def _fake_build(settings: Settings, built: FastAPI, *, on_drain: ServiceRuntime | None = None) -> ServiceServer:
        captured["app"] = built
        captured["on_drain"] = on_drain
        return cast("ServiceServer", _Server())

    monkeypatch.setattr(run_module, "build_server", _fake_build)
    run_module.run_service(_Factory)

    assert captured["app"] is app
    assert captured["on_drain"] is runtime
    assert captured["ran"] is True
