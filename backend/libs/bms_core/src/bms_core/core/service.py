"""core 层服务运行时基座：服务身份解析、日志绑定与停机摘流（02_02）。

- `ServiceIdentity`：服务身份数据对象（名称 / 版本 / 中文名），纳入 `BaseObject` 体系。
- `bind_service_identity`：把身份写入 structlog 全局上下文（`service` / `service_version`），
  经 `core/logging.py` 处理器链的 `merge_contextvars` 使业务日志与第三方 stdlib 日志每条自动携带。
- `ServiceRuntime`：应用级运行时——持有身份、暴露停机摘流标记 `draining`；`start_drain()` 幂等：
  置 `app.state.draining=True` 与 `app.state.startup_complete=False`（`/readyz` 随即返回 503 摘流），
  由启动入口的信号处理在 SIGTERM / SIGINT 到达时调用。
- `attach_service`：服务工厂接入助手——解析身份（服务包声明默认 + `[app].service` 可覆盖，
  配置为空时回写解析结果，供连接池按服务覆盖与租户库 `url_template` 的 `{service}` 占位取到正确服务名）
  → 绑定日志 → 构造运行时并落 `app.state`。

口径：本域只承载「服务是谁、怎么摘流」，不做进程编排（host / port / 信号接管见 `core/run.py`）；
探针响应读取身份见 `api/health.py`。
"""

from dataclasses import dataclass

import structlog
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings, get_settings
from bms_core.core.logging import get_logger

__all__ = [
    "ServiceIdentity",
    "ServiceRuntime",
    "attach_service",
    "bind_service_identity",
]


@dataclass(frozen=True)
class ServiceIdentity(BaseObject):
    """服务身份：名称（微服务名）、版本、中文名。"""

    name: str
    """服务名（用于日志 `service`、探针响应与按服务配置，如 `platform`）。"""

    version: str
    """服务版本（服务包 `__version__`）。"""

    title: str = ""
    """服务中文名（用于应用 title；可空）。"""


def bind_service_identity(identity: ServiceIdentity) -> None:
    """把服务身份写入 structlog 全局上下文（进程级；每条日志自动携带）。

    Args:
        identity: 服务身份。
    """
    structlog.contextvars.bind_contextvars(service=identity.name, service_version=identity.version)


class ServiceRuntime(BaseObject):
    """服务运行时：持身份、暴露停机摘流标记（应用级，单例落 `app.state.service_runtime`）。"""

    def __init__(self, app: FastAPI, identity: ServiceIdentity) -> None:
        """初始化：登记身份与初始（未摘流）状态。

        Args:
            app: 应用实例。
            identity: 服务身份。
        """
        self._app = app
        self._identity = identity
        app.state.service_runtime = self
        app.state.service_identity = identity
        app.state.draining = False

    @property
    def identity(self) -> ServiceIdentity:
        """服务身份。

        Returns:
            ServiceIdentity: 身份对象。
        """
        return self._identity

    @property
    def draining(self) -> bool:
        """是否正在停机摘流。

        Returns:
            bool: 摘流中 True。
        """
        return bool(getattr(self._app.state, "draining", False))

    def start_drain(self) -> None:
        """开始停机摘流（幂等）：置摘流标记并取消就绪（`/readyz` 随即 503）。"""
        if self.draining:
            return
        self._app.state.draining = True
        self._app.state.startup_complete = False
        get_logger("bms_core.service").info(
            "service_shutdown_started",
            service=self._identity.name,
            version=self._identity.version,
        )


def attach_service(
    app: FastAPI,
    *,
    declared_name: str,
    version: str,
    title: str = "",
    settings: Settings | None = None,
) -> ServiceRuntime:
    """接入服务运行时：解析身份 → 绑定日志 → 构造运行时并落 `app.state`。

    Args:
        app: 应用实例。
        declared_name: 服务包声明的默认服务名。
        version: 服务版本（服务包 `__version__`）。
        title: 服务中文名（可空）。
        settings: 应用配置（缺省取单例）。

    Returns:
        ServiceRuntime: 运行时实例。
    """
    resolved_settings = settings or get_settings()
    configured = resolved_settings.app.service.strip()
    name = configured or declared_name
    if not configured:
        # 配置为空：以服务包声明为准并回写，供连接池按服务覆盖与租户库模板取到正确服务名
        resolved_settings.app.service = name
    identity = ServiceIdentity(name=name, version=version, title=title)
    bind_service_identity(identity)
    return ServiceRuntime(app, identity)
