"""core 层日志基座接入点：统一日志门面与初始化入口（标准库占位）。

- `BaseLogger`：日志门面**中间层基类**（纳入 `BaseObject` 体系）。
- `StdoutLogger`：占位实现（标准库 logging，输出 **stdout、不落文件**）；
  真实 structlog 结构化 JSON / 上下文字段 / 脱敏归 03-2 日志体系。
- `configure_logging`：初始化入口（03-2 替换为 structlog 初始化）。
"""

import logging
import sys
from abc import ABC, abstractmethod

from app.core.base import BaseObject
from app.core.config import Settings

_HANDLER_MARKER = "_bms_stdout"


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
    def exception(self, event: str, **fields: object) -> None:
        """ERROR 日志（附当前异常堆栈）。"""


class StdoutLogger(BaseLogger):
    """标准库日志门面（占位）：输出 stdout、不落文件。"""

    def __init__(self, name: str = "bms", **fields: object) -> None:
        """初始化门面。

        Args:
            name: logger 名（模块级命名）。
            **fields: 预绑定上下文字段。
        """
        self._name = name
        self._fields: dict[str, object] = dict(fields)

    def bind(self, **fields: object) -> BaseLogger:
        """绑定上下文字段（返回新门面）。"""
        return StdoutLogger(self._name, **{**self._fields, **fields})

    def _emit(self, level: int, event: str, fields: dict[str, object], *, exc_info: bool = False) -> None:
        merged = {**self._fields, **fields}
        message = event if not merged else f"{event} {merged}"
        logging.getLogger(self._name).log(level, message, exc_info=exc_info)

    def debug(self, event: str, **fields: object) -> None:
        """DEBUG 日志。"""
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: object) -> None:
        """INFO 日志。"""
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: object) -> None:
        """WARNING 日志。"""
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: object) -> None:
        """ERROR 日志。"""
        self._emit(logging.ERROR, event, fields)

    def exception(self, event: str, **fields: object) -> None:
        """ERROR 日志（附当前异常堆栈）。"""
        self._emit(logging.ERROR, event, fields, exc_info=True)


def configure_logging(settings: Settings) -> None:
    """初始化日志（占位：标准库输出 stdout、不落文件）；03-2 替换为 structlog。

    Args:
        settings: 应用配置（取 `log.level`）。
    """
    level = getattr(logging, settings.log.level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _HANDLER_MARKER, True)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)


def get_logger(name: str = "bms") -> BaseLogger:
    """取日志门面（模块级统一入口）。

    Args:
        name: logger 名。

    Returns:
        BaseLogger: 日志门面。
    """
    return StdoutLogger(name)
