"""服务启动入口测试：hypercorn 配置 / 信号先摘流 / 二次强退（Kiwi 2419）。"""

import asyncio
import signal
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from hypercorn.config import Config

from bms_core.core import run as run_module
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.factory import BaseApplicationFactory
from bms_core.core.run import (
    _install_signal_handlers,  # pyright: ignore[reportPrivateUsage]
    _restore_signal_handlers,  # pyright: ignore[reportPrivateUsage]
    _SignalController,  # pyright: ignore[reportPrivateUsage]
    build_config,
    serve_service,
)
from bms_core.core.service import ServiceIdentity, ServiceRuntime


@pytest.mark.kiwi_id(2419)
def test_build_config_uses_server_settings() -> None:
    """启动配置取 `[server]`：bind / workers / 日志关闭 / 优雅停机超时。"""
    settings = Settings()
    settings.server.host = "127.0.0.1"
    settings.server.port = 9999
    settings.server.graceful_timeout_seconds = 45
    config = build_config(settings)
    assert config.bind == ["127.0.0.1:9999"]
    assert config.workers == 1
    assert config.graceful_timeout == 45.0
    assert config.accesslog is None
    assert config.errorlog is None
    assert config.ssl_enabled is False


@pytest.mark.kiwi_id(2419)
def test_build_config_maps_connection_limits() -> None:
    """连接层四项映射到 hypercorn（默认值与 hypercorn 缺省一致，改配置才改变行为）。"""
    defaults = build_config(Settings())
    assert defaults.h2_max_concurrent_streams == 100
    assert defaults.h2_max_header_list_size == 65_536
    assert defaults.keep_alive_timeout == 5.0
    assert defaults.keep_alive_max_requests == 1_000

    settings = Settings()
    settings.server.h2_max_concurrent_streams = 256
    settings.server.h2_max_header_list_size = 131_072
    settings.server.keep_alive_timeout_seconds = 30
    settings.server.keep_alive_max_requests = 10
    config = build_config(settings)
    assert config.h2_max_concurrent_streams == 256
    assert config.h2_max_header_list_size == 131_072
    assert config.keep_alive_timeout == 30.0
    assert config.keep_alive_max_requests == 10


@pytest.mark.kiwi_id(2419)
def test_build_config_maps_tls(tmp_path: Path) -> None:
    """TLS 两字段映射到 hypercorn 配置（同给同空由 Settings 校验）。"""
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    settings = Settings()
    settings.server.certfile = str(cert)
    settings.server.keyfile = str(key)
    config = build_config(settings)
    assert config.certfile == str(cert)
    assert config.keyfile == str(key)
    assert config.ssl_enabled is True


@pytest.mark.kiwi_id(2419)
def test_build_config_rejects_missing_tls_file(tmp_path: Path) -> None:
    """证书 / 私钥路径不存在时拒启并指出字段。"""
    settings = Settings()
    settings.server.certfile = str(tmp_path / "missing-cert.pem")
    settings.server.keyfile = str(tmp_path / "missing-key.pem")
    with pytest.raises(ConfigError, match="certfile"):
        build_config(settings)


@pytest.mark.kiwi_id(2419)
def test_signal_controller_drains_then_sets_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一次信号：先摘流再置停机事件；第二次信号：强退。"""
    app = FastAPI()
    app.state.startup_complete = True
    runtime = ServiceRuntime(app, ServiceIdentity(name="platform", version="0.1.0"))
    event = asyncio.Event()
    controller = _SignalController(shutdown_event=event, on_drain=runtime)

    controller.handle(signal.SIGTERM)

    assert runtime.draining is True
    assert app.state.startup_complete is False
    assert event.is_set()

    exits: ConcurrentStableList[int] = ConcurrentStableList()

    def _fake_exit(code: int) -> None:
        exits.add(code)

    monkeypatch.setattr(run_module.os, "_exit", _fake_exit)
    controller.handle(signal.SIGTERM)
    assert list(exits) == [1]


@pytest.mark.kiwi_id(2419)
def test_signal_controller_without_runtime_only_sets_event() -> None:
    """未接入运行时：仍触发停机事件，不抛错。"""
    event = asyncio.Event()
    controller = _SignalController(shutdown_event=event, on_drain=None)
    controller.handle(signal.SIGTERM)
    assert event.is_set()


@pytest.mark.kiwi_id(2419)
def test_serve_service_uses_hypercorn(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动流程：构造 hypercorn 配置 → 安装信号 → await serve → 恢复信号。"""
    app = FastAPI()
    settings = Settings()
    captured: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    async def _fake_serve(served_app: FastAPI, config: Config, *, shutdown_trigger: object) -> None:
        captured.set("app", served_app)
        captured.set("config", config)
        captured.set("trigger", shutdown_trigger)

    monkeypatch.setattr(run_module, "serve", _fake_serve)

    def _fake_install(loop: asyncio.AbstractEventLoop, handler: Any) -> ConcurrentStableList[tuple[int, Any]]:
        del loop, handler
        return ConcurrentStableList()

    monkeypatch.setattr(run_module, "_install_signal_handlers", _fake_install)

    def _fake_restore(loop: object, installed: object) -> None:
        captured.set("restored", True)

    monkeypatch.setattr(run_module, "_restore_signal_handlers", _fake_restore)

    asyncio.run(serve_service(app, settings))

    assert captured["app"] is app
    config = cast("Config", captured["config"])
    assert config.bind == ["0.0.0.0:8000"]
    assert captured["restored"] is True


@pytest.mark.kiwi_id(2419)
def test_run_service_builds_app_and_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    """启动主流程：构造应用 → 取停机回调 → 转交 `serve_service`。"""
    app = FastAPI()
    app.state.startup_complete = True
    runtime = ServiceRuntime(app, ServiceIdentity(name="platform", version="0.1.0"))

    class _Factory(BaseApplicationFactory):
        def create(self, options: None = None) -> FastAPI:
            return app

    captured: ConcurrentStableDict[str, object] = ConcurrentStableDict()

    async def _fake_serve(served_app: FastAPI, settings: Settings, *, on_drain: ServiceRuntime | None = None) -> None:
        captured.set("app", served_app)
        captured.set("settings", settings)
        captured.set("on_drain", on_drain)

    def _fake_configure(settings: Settings) -> None:
        del settings
        captured.set("configured", True)

    monkeypatch.setattr(run_module, "serve_service", _fake_serve)
    monkeypatch.setattr(run_module, "get_settings", Settings)
    monkeypatch.setattr(run_module, "configure_logging", _fake_configure)

    run_module.run_service(_Factory)

    assert captured["app"] is app
    assert captured["on_drain"] is runtime


class _FakeSignalLoop:
    """信号处理器安装 / 恢复用的假事件循环。"""

    def __init__(
        self,
        *,
        supported: bool = True,
        fail_on: tuple[int, ...] = (),  # bare-collections:allow（假事件循环的失败信号集合）
    ) -> None:
        self.supported = supported
        self.fail_on = fail_on
        self.added: ConcurrentStableList[int] = ConcurrentStableList()
        self.removed: ConcurrentStableList[int] = ConcurrentStableList()
        self.forwarded: ConcurrentStableList[Any] = ConcurrentStableList()

    def add_signal_handler(self, sig: int, handler: Any, *args: Any) -> None:
        del handler, args
        if not self.supported:
            raise NotImplementedError
        self.added.add(sig)

    def remove_signal_handler(self, sig: int) -> None:
        if sig in self.fail_on:
            raise RuntimeError
        self.removed.add(sig)

    def call_soon_threadsafe(self, handler: Any, *args: Any) -> None:
        self.forwarded.add((handler, args))


def _noop_handler(sig: int) -> None:
    del sig


@pytest.mark.kiwi_id(2419)
def test_build_config_rejects_half_tls() -> None:
    """直接调用启动器时，TLS 半配置同样拒启（不只依赖 Settings 校验）。"""
    settings = Settings()
    settings.server.certfile = "cert.pem"
    with pytest.raises(ConfigError, match="certfile"):
        build_config(settings)


@pytest.mark.kiwi_id(2419)
def test_install_signal_handlers_prefers_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件循环可用时优先 `add_signal_handler`；不存在的信号名跳过。"""
    monkeypatch.setattr(run_module, "SIGNAL_NAMES", ("SIGTERM", "NOT_A_SIGNAL"))
    loop = _FakeSignalLoop()
    installed = _install_signal_handlers(cast("Any", loop), _noop_handler)
    assert list(installed) == [(signal.SIGTERM, None)]
    assert list(loop.added) == [signal.SIGTERM]


@pytest.mark.kiwi_id(2419)
def test_install_signal_handlers_falls_back_to_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件循环不支持时回退 `signal.signal`，转发线程安全地回到事件循环。"""
    monkeypatch.setattr(run_module, "SIGNAL_NAMES", ("SIGTERM",))
    registered: ConcurrentStableList[tuple[int, Any]] = ConcurrentStableList()

    def _fake_getsignal(sig: int) -> object:
        del sig
        return "previous"

    def _fake_signal(sig: int, handler: Any) -> None:
        registered.add((sig, handler))

    monkeypatch.setattr(run_module.signal, "getsignal", _fake_getsignal)
    monkeypatch.setattr(run_module.signal, "signal", _fake_signal)

    loop = _FakeSignalLoop(supported=False)
    installed = _install_signal_handlers(cast("Any", loop), _noop_handler)

    assert list(installed) == [(signal.SIGTERM, "previous")]
    forward = registered[0][1]
    forward(signal.SIGTERM, None)
    assert list(loop.forwarded) == [(_noop_handler, (signal.SIGTERM,))]


@pytest.mark.kiwi_id(2419)
def test_restore_signal_handlers_skips_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """恢复时忽略移除失败；有原处理器的信号写回。"""
    loop = _FakeSignalLoop(fail_on=(signal.SIGINT,))
    restored: ConcurrentStableList[tuple[int, Any]] = ConcurrentStableList()

    def _fake_signal(sig: int, handler: Any) -> None:
        restored.add((sig, handler))

    monkeypatch.setattr(run_module.signal, "signal", _fake_signal)
    installed: ConcurrentStableList[tuple[int, Any]] = ConcurrentStableList(
        [(signal.SIGTERM, "previous"), (signal.SIGINT, None)]
    )

    _restore_signal_handlers(cast("Any", loop), installed)

    assert list(loop.removed) == [signal.SIGTERM]
    assert list(restored) == [(signal.SIGTERM, "previous")]
