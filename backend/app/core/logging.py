"""core 层日志基座：structlog 统一日志门面与初始化入口。

- `BaseLogger`：日志门面**中间层基类**（纳入 `BaseObject` 体系）。
- `StdoutLogger`：门面实现（structlog 绑定日志器，输出 **stdout、不落文件**）。
- `configure_logging`：初始化入口——structlog 处理器链（上下文 / 级别 / logger / 时间戳 / 堆栈 / 脱敏）、
  `dev` console 与 `test` / `prod` JSON 渲染、stdlib / uvicorn 统一渲染、`uvicorn.access` 关闭
  （访问行由请求日志中间件统一输出，避免重复）。
- 上下文字段（`trace_id` / `request_id` / `tenant` / `user_id` / `client_ip`）由 `_add_context_fields`
  从 `core/context.py` 读取；`_redact_sensitive` 对敏感键名与连接串密码统一脱敏（不落原始值）。
"""

import logging
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.core.base import BaseObject
from app.core.config import Settings
from app.core.context import (
    current_user_id,
    get_current_client_ip,
    get_current_request_id,
    get_current_tenant,
    get_current_trace_id,
)

_HANDLER_MARKER = "_bms_structlog"
_MASK = "***"
_SENSITIVE_KEYS = frozenset(
    {
        "access_key",
        "access_token",
        "api_key",
        "authorization",
        "captcha",
        "captcha_code",
        "client_secret",
        "cookie",
        "password",
        "passwd",
        "private_key",
        "pwd",
        "refresh_token",
        "secret",
        "secret_key",
        "token",
    }
)
_SENSITIVE_SUFFIXES = ("_password", "_passwd", "_secret", "_token")
_CONN_PASSWORD_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://[^:/@\s]+:)([^@/\s]+)(@)")
_MAX_REDACT_DEPTH = 5


def _add_context_fields(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """注入请求上下文字段（已显式给出的键不覆盖）。

    Args:
        _logger: 下游日志器（未使用）。
        _name: 日志器名（未使用）。
        event_dict: 日志事件字典。

    Returns:
        EventDict: 注入上下文字段后的事件字典。
    """
    context_fields: tuple[tuple[str, object], ...] = (
        ("trace_id", get_current_trace_id()),
        ("request_id", get_current_request_id()),
        ("tenant", get_current_tenant()),
        ("user_id", current_user_id.get()),
        ("client_ip", get_current_client_ip()),
    )
    for key, value in context_fields:
        if value is not None:
            event_dict.setdefault(key, value)
    return event_dict


def _add_timestamp(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """注入本地时区 ISO8601 时间戳（`ts` 字段，含时区偏移，如 `+08:00`）。"""
    event_dict.setdefault("ts", datetime.now().astimezone().isoformat())
    return event_dict


def _is_sensitive_key(key: str) -> bool:
    """判断键名是否命中敏感黑名单（忽略大小写，含后缀形态）。"""
    lowered = key.lower()
    return lowered in _SENSITIVE_KEYS or lowered.endswith(_SENSITIVE_SUFFIXES)


def _redact_value(value: Any, depth: int) -> Any:
    """递归脱敏值中的连接串密码与嵌套敏感键（限深）。"""
    if isinstance(value, str):
        return _CONN_PASSWORD_RE.sub(_replace_conn_password, value)
    if depth >= _MAX_REDACT_DEPTH:
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return {
            key: _MASK if isinstance(key, str) and _is_sensitive_key(key) else _redact_value(item, depth + 1)
            for key, item in mapping.items()
        }
    if isinstance(value, (list, tuple)):
        sequence = cast("list[object] | tuple[object, ...]", value)
        return [_redact_value(item, depth + 1) for item in sequence]
    return value


def _replace_conn_password(match: re.Match[str]) -> str:
    """连接串密码替换为掩码。"""
    return f"{match.group(1)}{_MASK}{match.group(3)}"


def _redact_sensitive(_logger: WrappedLogger, _name: str, event_dict: EventDict) -> EventDict:
    """敏感键名值替换掩码；其余值扫描连接串密码（含嵌套结构）。

    Args:
        _logger: 下游日志器（未使用）。
        _name: 日志器名（未使用）。
        event_dict: 日志事件字典。

    Returns:
        EventDict: 脱敏后的事件字典。
    """
    for key in list(event_dict):
        if _is_sensitive_key(key):
            event_dict[key] = _MASK
        else:
            event_dict[key] = _redact_value(event_dict[key], depth=0)
    return event_dict


class BaseLogger(BaseObject, ABC):
    """日志门面中间层基类：统一日志接入点与上下文绑定。"""

    @abstractmethod
    def bind(self, **fields: object) -> BaseLogger:
        """绑定上下文字段（返回新门面，不影响原实例）。"""

    @abstractmethod
    def debug(self, event: str, **fields: object) -> None:
        """DEBUG 日志。"""

    @abstractmethod
    def info(self, event: str, **fields: object) -> None:
        """INFO 日志。"""

    @abstractmethod
    def warning(self, event: str, **fields: object) -> None:
        """WARNING 日志。"""

    @abstractmethod
    def error(self, event: str, **fields: object) -> None:
        """ERROR 日志。"""

    @abstractmethod
    def critical(self, event: str, **fields: object) -> None:
        """CRITICAL 日志（系统级故障）。"""

    @abstractmethod
    def exception(self, event: str, **fields: object) -> None:
        """ERROR 日志（附当前异常堆栈）。"""


class StdoutLogger(BaseLogger):
    """structlog 日志门面：输出 stdout、不落文件。

    结构化渲染形态由 `configure_logging` 按 `[log].format` 统一配置
    （`dev` console 可读 / `test`·`prod` 单行 JSON）。
    """

    def __init__(self, name: str = "bms", **fields: object) -> None:
        """初始化门面。

        Args:
            name: logger 名（模块级命名）。
            **fields: 预绑定上下文字段。
        """
        self._name = name
        self._fields: dict[str, object] = dict(fields)
        self._logger = structlog.get_logger(name)

    def bind(self, **fields: object) -> BaseLogger:
        """绑定上下文字段（返回新门面）。"""
        return StdoutLogger(self._name, **{**self._fields, **fields})

    def _emit(self, fields: dict[str, object]) -> Any:
        return self._logger.bind(**{**self._fields, **fields})

    def debug(self, event: str, **fields: object) -> None:
        """DEBUG 日志。"""
        self._emit(fields).debug(event)

    def info(self, event: str, **fields: object) -> None:
        """INFO 日志。"""
        self._emit(fields).info(event)

    def warning(self, event: str, **fields: object) -> None:
        """WARNING 日志。"""
        self._emit(fields).warning(event)

    def error(self, event: str, **fields: object) -> None:
        """ERROR 日志。"""
        self._emit(fields).error(event)

    def critical(self, event: str, **fields: object) -> None:
        """CRITICAL 日志。"""
        self._emit(fields).critical(event)

    def exception(self, event: str, **fields: object) -> None:
        """ERROR 日志（附当前异常堆栈）。"""
        self._emit(fields).exception(event)


def _build_processors() -> list[Processor]:
    """组装处理器链（业务日志与第三方 stdlib 日志共用）。"""
    return [
        _add_context_fields,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_timestamp,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _redact_sensitive,
    ]


def _build_renderer(settings: Settings) -> Processor:
    """按 `[log].format` 选择渲染器（console 可读 / JSON 单行）。"""
    if settings.log.format == "console":
        return structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    return structlog.processors.JSONRenderer(ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    """初始化结构化日志（幂等；渲染形态由 `[log].format` 控制）。

    Args:
        settings: 应用配置（取 `log.level` / `log.format`）。
    """
    processors = _build_processors()
    structlog.configure(
        processors=[*processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, _build_renderer(settings)],
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log.level.upper(), logging.INFO))
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


def get_logger(name: str = "bms") -> BaseLogger:
    """取日志门面（模块级统一入口）。

    Args:
        name: logger 名（模块名）。

    Returns:
        BaseLogger: 日志门面。
    """
    return StdoutLogger(name)
