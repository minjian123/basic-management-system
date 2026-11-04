"""core 层服务启动入口：配置驱动的 hypercorn 启动与信号优先摘流（02_04）。

- `build_config`：按 `[server]` 构造 hypercorn 配置——host / port、可选 TLS（certfile / keyfile）、
  `graceful_timeout_seconds`、单进程（`workers=1`）与关闭自带 access / error 日志（统一走 structlog）。
- `serve_service`：安装信号接管后调用 hypercorn `serve`。第一次 SIGTERM / SIGINT 先调停机回调
  （`ServiceRuntime.start_drain`，`/readyz` 立即 503 摘流），再触发 hypercorn 正常停机
  （关闭监听 → 等待在途至 `graceful_timeout_seconds` → lifespan shutdown）；第二次信号直接强退。
- `run_service`：服务启动入口主流程——取配置 → 初始化日志 → 构造应用 → 从应用运行时取停机回调 → 启动。
  各服务 `__main__.py` 只需 `run_service(ApplicationFactory)`，命令统一为 `python -m bms_<服务名>`。

口径：入口按单进程启动（hypercorn `serve` 忽略 `workers>1`），信号摘流可靠；多副本由 Docker Compose /
K8s 横向扩容承担（一服务一容器）。HTTP/2 在明文下走 h2c prior knowledge，配置 TLS 后由 ALPN 协商 h2。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path
from types import FrameType
from typing import Any

from fastapi import FastAPI

# hypercorn 的 ASGI 类型与 starlette 的 Scope / Receive / Send 协议不同源（上游未对齐），
# 严格模式下导入与调用各有一处类型告警；运行时无影响，按仓库既有口径做细粒度忽略。
from hypercorn.asyncio import serve  # pyright: ignore[reportUnknownVariableType]
from hypercorn.config import Config

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.exceptions import ConfigError
from bms_core.core.factory import BaseApplicationFactory
from bms_core.core.logging import configure_logging, get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.core.service import ServiceRuntime

__all__ = [
    "build_config",
    "run_service",
    "serve_service",
]

SIGNAL_NAMES = ("SIGTERM", "SIGINT", "SIGBREAK")
"""需要接管的信号名（`SIGBREAK` 仅 Windows 存在，按 `getattr` 跳过）。"""


class _SignalController(BaseFrameworkObject):
    """信号控制器：第一次摘流并触发停机，第二次强退。"""

    def __init__(self, *, shutdown_event: asyncio.Event, on_drain: ServiceRuntime | None) -> None:
        """初始化。

        Args:
            shutdown_event: hypercorn 的停机触发事件（置位后开始优雅停机）。
            on_drain: 停机回调（信号到达时先调用；缺省不摘流，仅正常停机）。
        """
        self._shutdown_event = shutdown_event
        self._on_drain = on_drain
        self._signals = 0

    def handle(self, sig: int) -> None:
        """处理一次信号。

        Args:
            sig: 信号编号。
        """
        self._signals += 1
        if self._signals == 1:
            if self._on_drain is not None:
                self._on_drain.start_drain()
            self._shutdown_event.set()
            return
        get_logger("bms_core.run").warning("service_force_exit", signal=sig, signal_count=self._signals)
        os._exit(1)


def build_config(settings: Settings) -> Config:
    """按 `[server]` 构造 hypercorn 配置。

    Args:
        settings: 应用配置。

    Returns:
        Config: hypercorn 配置（尚未启动）。

    Raises:
        ConfigError: TLS 证书 / 私钥只给一个，或给定路径不存在 / 不是文件。
    """
    certfile = settings.server.certfile.strip()
    keyfile = settings.server.keyfile.strip()
    if bool(certfile) != bool(keyfile):
        raise ConfigError("[server].certfile 与 [server].keyfile 必须同时配置或同时留空")
    if certfile:
        for field_name, path in (("certfile", certfile), ("keyfile", keyfile)):
            if not Path(path).is_file():
                raise ConfigError(f"[server].{field_name} 不存在或不是文件：{path}")

    config = Config()
    config.bind = [f"{settings.server.host}:{settings.server.port}"]
    config.workers = 1
    config.accesslog = None
    config.errorlog = None
    config.loglevel = settings.log.level
    config.graceful_timeout = float(settings.server.graceful_timeout_seconds)
    config.certfile = certfile or None
    config.keyfile = keyfile or None
    return config


def _install_signal_handlers(loop: asyncio.AbstractEventLoop, handler: Any) -> ConcurrentStableList[tuple[int, Any]]:
    """安装 SIGTERM / SIGINT / SIGBREAK 处理器（Windows 回退 `signal.signal`）。

    Args:
        loop: 当前事件循环。
        handler: 信号处理函数（接收信号编号）。

    Returns:
        ConcurrentStableList[tuple[int, Any]]: `(信号编号, 原处理器)` 列表；原处理器为 None
        表示由事件循环托管（恢复时 `remove_signal_handler`）。
    """
    installed: ConcurrentStableList[tuple[int, Any]] = ConcurrentStableList()
    for name in SIGNAL_NAMES:
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, handler, sig)
        except NotImplementedError:
            previous = signal.getsignal(sig)

            def _forward(signum: int, frame: FrameType | None) -> None:
                del frame
                loop.call_soon_threadsafe(handler, signum)

            signal.signal(sig, _forward)
            installed.add((sig, previous))
        else:
            installed.add((sig, None))
    return installed


def _restore_signal_handlers(loop: asyncio.AbstractEventLoop, installed: ConcurrentStableList[tuple[int, Any]]) -> None:
    """恢复安装前的信号处理器（测试可重复调用）。

    Args:
        loop: 当前事件循环。
        installed: `_install_signal_handlers` 的返回值。
    """
    for sig, previous in installed:
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.remove_signal_handler(sig)
        if previous is not None:
            signal.signal(sig, previous)


async def serve_service(app: FastAPI, settings: Settings, *, on_drain: ServiceRuntime | None = None) -> None:
    """以 hypercorn 启动服务（含信号先摘流与二次强退）。

    Args:
        app: 应用实例。
        settings: 应用配置（读取 `[server]`）。
        on_drain: 停机回调（缺省不摘流，仅正常停机）。
    """
    config = build_config(settings)
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    controller = _SignalController(shutdown_event=shutdown_event, on_drain=on_drain)
    installed = _install_signal_handlers(loop, controller.handle)
    get_logger("bms_core.run").info(
        "service_listening",
        host=settings.server.host,
        port=settings.server.port,
        tls=config.ssl_enabled,
        http2=True,
    )
    try:
        await serve(app, config, shutdown_trigger=shutdown_event.wait)  # pyright: ignore[reportArgumentType]
    finally:
        _restore_signal_handlers(loop, installed)


def run_service(factory: type[BaseApplicationFactory]) -> None:
    """启动服务（`python -m bms_<服务名>` 的入口主流程）。

    Args:
        factory: 服务应用工厂类。
    """
    settings = get_settings()
    configure_logging(settings)
    app = factory().create(None)
    runtime = getattr(app.state, "service_runtime", None)
    on_drain = runtime if isinstance(runtime, ServiceRuntime) else None
    asyncio.run(serve_service(app, settings, on_drain=on_drain))
