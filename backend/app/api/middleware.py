"""api 层中间件：入站链路 id（`X-Trace-Id`）与请求日志（访问 / 慢请求 / 探针排除）。

- `TraceIdMiddleware`：纯 ASGI 中间件——读入站 `X-Trace-Id`（缺失回退当前 request_id，再缺失生成 32 位 hex）、
  写入 `core/context.py` 的 `current_trace_id`（日志体系与审计统一取值），并回写响应头；请求结束复位。
- `RequestLoggingMiddleware`：纯 ASGI 中间件——每请求生成 `request_id`（uuid4 hex）并解析 `client_ip` 写入上下文；
  请求结束输出单行访问日志（普通 INFO `request`，超 `slow_request_ms` 整行 WARNING `slow_request`）；
  探针（`/healthz`、`/readyz`）与文档路径（`/docs`、`/redoc`、`/openapi.json`）排除，任何级别不记。

口径：
- **必须为纯 ASGI 中间件**（不经 `BaseHTTPMiddleware`）：后者把下游应用放在独立任务中执行，
  中间件内设置的上下文变量传不到接口内（与 02-3-5「同步生成器依赖经线程池执行导致上下文丢失」同类问题）。
- `client_ip` 取 `X-Forwarded-For` 首值（兼容 nginx 反代）、兜底连接地址；仅日志展示，不作安全判定。
- 未捕获异常由全局异常处理器记 ERROR（含堆栈），本中间件照常记录 `status=500` 访问行。
"""

import time
import uuid
from collections.abc import Mapping
from contextvars import Token

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.base import BaseObject
from app.core.context import (
    get_current_request_id,
    reset_current_client_ip,
    reset_current_request_id,
    reset_current_trace_id,
    reset_read_only,
    set_current_client_ip,
    set_current_request_id,
    set_current_trace_id,
    set_read_only,
)
from app.core.logging import get_logger
from app.db.routing import is_read_method
from app.tracing.base import TRACE_ID_HEADER, new_trace_id

__all__ = ["ReadOnlyMiddleware", "RequestLoggingMiddleware", "TraceIdMiddleware"]

_EXCLUDED_PATHS = frozenset({"/healthz", "/readyz", "/docs", "/redoc", "/openapi.json"})


class TraceIdMiddleware(BaseObject):
    """入站链路 id 中间件（纯 ASGI）：读请求头 → 缺省生成 → 上下文 → 回写响应头。"""

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = Headers(scope=scope).get(TRACE_ID_HEADER) or get_current_request_id() or new_trace_id()
        scope.setdefault("state", {})["trace_id"] = trace_id
        token = set_current_trace_id(trace_id)

        async def _send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, _send_with_trace_id)
        finally:
            reset_current_trace_id(token)


class ReadOnlyMiddleware(BaseObject):
    """只读标记中间件（纯 ASGI）：按 HTTP 方法设置 `read_only` 上下文（GET/HEAD/OPTIONS 只读）。

    路由显式覆盖：只读数据集 / 强制从库接口声明 `Depends(get_read_db)`，写 / 事务声明
    `Depends(get_write_db)` 或 `Depends(get_uow)`。
    """

    def __init__(self, app: ASGIApp) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = set_read_only(is_read_method(scope.get("method")))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_read_only(token)


class RequestLoggingMiddleware(BaseObject):
    """请求日志中间件（纯 ASGI）：request_id / client_ip 上下文 + 单行访问日志（慢请求升 WARNING）。"""

    def __init__(self, app: ASGIApp, slow_request_ms: int = 1000) -> None:
        """初始化中间件。

        Args:
            app: 下游 ASGI 应用。
            slow_request_ms: 慢请求阈值（毫秒，取自 `[log].slow_request_ms`）。
        """
        self.app = app
        self.slow_request_ms = slow_request_ms

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理请求（非 HTTP 作用域直通）。

        Args:
            scope: ASGI 作用域。
            receive: 接收通道。
            send: 发送通道。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        request_token: Token[str | None] = set_current_request_id(request_id)
        client_token: Token[str | None] = set_current_client_ip(_client_ip(scope))
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status_code = 0

        async def _send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, _send_with_status)
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._log_request(scope, status_code, duration_ms)
            reset_current_client_ip(client_token)
            reset_current_request_id(request_token)

    def _log_request(self, scope: Scope, status_code: int, duration_ms: float) -> None:
        """输出单行访问日志（排除清单内不记；超阈值升 WARNING）。

        链路 id 从请求态读取（`TraceIdMiddleware` 已复位上下文，请求态不受复位影响）。
        """
        path = str(scope.get("path", ""))
        if path in _EXCLUDED_PATHS:
            return
        logger = get_logger("app.request")
        fields: dict[str, object] = {
            "method": scope.get("method", ""),
            "path": path,
            "status": status_code,
            "duration_ms": duration_ms,
        }
        state: Mapping[str, object] = scope.get("state", {})
        if trace_id := state.get("trace_id"):
            fields["trace_id"] = trace_id
        if duration_ms >= self.slow_request_ms:
            logger.warning("slow_request", **fields)
        else:
            logger.info("request", **fields)


def _client_ip(scope: Scope) -> str | None:
    """解析来源 IP（`X-Forwarded-For` 首值 → 连接地址）。"""
    forwarded = Headers(scope=scope).get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return str(client[0]) if client else None
