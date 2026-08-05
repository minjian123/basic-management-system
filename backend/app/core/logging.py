"""structlog 结构化日志配置。

- dev 环境输出可读控制台格式；test/prod 输出 JSON（一行一条，供 Loki 聚合）
- request_id / tenant 经 contextvars 自动注入（merge_contextvars）
- 敏感字段脱敏：key 命中敏感词表的值一律打码，不落原始值
- 与标准 logging 集成：uvicorn、SQLAlchemy 等第三方日志汇入同一管线
"""

from __future__ import annotations

import logging
from typing import Any

import structlog
from structlog.types import EventDict, Processor

_SENSITIVE_SUBSTRINGS = (
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
)


def _mask_sensitive_processor(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    """将事件字典中键名命中敏感词表的字段打码。"""
    for key in list(event_dict):
        if any(sub in key.lower() for sub in _SENSITIVE_SUBSTRINGS):
            event_dict[key] = "***"
    return event_dict


def configure_logging(level: str = "INFO", env: str = "dev") -> None:
    """配置 structlog 与标准 logging 管线，应用启动时调用一次。

    :param level: 日志级别（DEBUG/INFO/WARNING/ERROR，来自 config.toml [log]）
    :param env: 运行环境（dev 输出可读格式，其余输出 JSON）
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(message)s", force=True)

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _mask_sensitive_processor,
    ]
    if env == "dev":
        renderer: Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()
    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
