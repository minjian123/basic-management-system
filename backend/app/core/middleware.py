"""请求中间件：request_id 注入、租户解析与上下文写入、访问日志。

- request_id：沿用客户端 X-Request-ID（不存在时生成 uuid hex 前 12 位），写入 contextvars，
  响应头回带 X-Request-ID 便于排查
- 租户解析：健康检查与平台级路径跳过，其余请求按 core/tenant.py 规则解析并写入上下文
- 访问日志：method/path/status/cost_ms，经 structlog 输出（生产 JSON）
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .context import get_request_id, set_request_id, set_tenant
from .errors import BizError, error_body
from .tenant import parse_tenant

logger = structlog.get_logger("bms.middleware")

_PLATFORM_PATHS = ("/healthz", "/readyz")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """请求上下文中间件。"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            if not request.url.path.startswith(_PLATFORM_PATHS):
                parse_tenant(request)
            else:
                set_tenant(None)
            response = await call_next(request)
        except BizError as exc:
            # 中间件层业务异常（如租户校验失败）不经路由异常处理器，在此转统一响应
            response = JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))
        except Exception:
            logger.exception(
                "request failed",
                method=request.method,
                path=request.url.path,
            )
            raise
        cost_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            request_id=get_request_id(),
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            cost_ms=cost_ms,
        )
        return response
