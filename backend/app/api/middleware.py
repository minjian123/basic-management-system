"""api 层中间件：入站链路 id 生成 / 透传（`X-Trace-Id`）。

- `TraceIdMiddleware`：纯 ASGI 中间件——读入站 `X-Trace-Id`（缺失则生成 32 位 hex）、
  写入 `core/context.py` 的 `current_trace_id`（日志体系与审计统一取值），并回写响应头；请求结束复位。

口径：
- **必须为纯 ASGI 中间件**（不经 `BaseHTTPMiddleware`）：后者把下游应用放在独立任务中执行，
  中间件内设置的上下文变量传不到接口内（与 02-3-5「同步生成器依赖经线程池执行导致上下文丢失」同类问题）。
- 本中间件只做**链路 id 贯穿**（不采样、不上报）；出站透传、otel-collector / Jaeger 上报随回补阶段接入。
"""

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.base import BaseObject
from app.core.context import reset_current_trace_id, set_current_trace_id
from app.tracing.base import TRACE_ID_HEADER, new_trace_id

__all__ = ["TraceIdMiddleware"]


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

        trace_id = Headers(scope=scope).get(TRACE_ID_HEADER) or new_trace_id()
        token = set_current_trace_id(trace_id)

        async def _send_with_trace_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, _send_with_trace_id)
        finally:
            reset_current_trace_id(token)
