"""core 层服务启动入口：配置驱动的 uvicorn 启动与信号优先摘流（02_02）。

- `ServiceServer`：`uvicorn.Server` 子类——覆写 `handle_exit`，在 uvicorn 处理 SIGTERM / SIGINT 前
  先调用停机回调（`ServiceRuntime.start_drain`，信号到达即置 `draining`，`/readyz` 立即 503 摘流），
  再链式调用父类完成优雅收尾（停止接收新连接 → 等待在途完成 → lifespan shutdown 释放资源）。
- `build_server`：按 `[server]` 的 `host` / `port` 构造 uvicorn 配置与 `ServiceServer`；
  日志统一走 structlog（`log_config=None` / `access_log=False`）。
- `run_service`：服务启动入口主流程——取配置 → 初始化日志 → 构造应用 → 从应用运行时取停机回调 → 启动。
  各服务 `__main__.py` 只需 `run_service(ApplicationFactory)`，命令统一为 `python -m bms_<服务名>`。

口径：入口按单进程（`workers=1`）启动，信号摘流可靠；多副本 / 多 worker 由 Docker Compose / K8s
横向扩容承担（一服务一容器）。
"""

from types import FrameType

import uvicorn
from fastapi import FastAPI

from bms_core.core.config import Settings, get_settings
from bms_core.core.factory import BaseApplicationFactory
from bms_core.core.logging import configure_logging
from bms_core.core.service import ServiceRuntime

__all__ = [
    "ServiceServer",
    "build_server",
    "run_service",
]


class ServiceServer(uvicorn.Server):
    """uvicorn 服务器子类：信号到达先摘流，再走默认优雅收尾。"""

    def __init__(self, config: uvicorn.Config, *, on_drain: ServiceRuntime | None = None) -> None:
        """初始化。

        Args:
            config: uvicorn 配置。
            on_drain: 停机回调（信号到达时先调用；缺省不摘流，仅默认停机）。
        """
        super().__init__(config)
        self._on_drain = on_drain

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """信号处理：先触发停机摘流，再交父类置退出标志。

        Args:
            sig: 信号编号。
            frame: 当前栈帧（未使用）。
        """
        if self._on_drain is not None:
            self._on_drain.start_drain()
        super().handle_exit(sig, frame)


def build_server(settings: Settings, app: FastAPI, *, on_drain: ServiceRuntime | None = None) -> ServiceServer:
    """按配置构造 uvicorn 服务器（host / port 取 `[server]`；日志走 structlog）。

    Args:
        settings: 应用配置。
        app: 应用实例。
        on_drain: 停机回调。

    Returns:
        ServiceServer: 服务器实例（尚未启动）。
    """
    config = uvicorn.Config(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,
        access_log=False,
    )
    return ServiceServer(config, on_drain=on_drain)


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
    build_server(settings, app, on_drain=on_drain).run()
