"""统一异常与响应结构。

- BizError：业务异常（错误码 + 开发者消息），全局异常处理器统一转换为 {code, message, data}
- HTTP 状态码与业务错误码分离：状态码表达传输层语义（400/404/500），code 表达业务语义
- 错误码 5 位，万位为模块段（见《项目规划说明》API 设计规范节）：
  1xxxx 通用（参数校验、限流、系统内部）、8xxxx 开放接口/租户/SSO
- 新增错误码必须先登记此处，禁止复用旧码；文案由前端按 i18n 映射，message 仅供开发与联调
"""

from __future__ import annotations

from typing import Any, cast

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import get_request_id

logger = structlog.get_logger("bms.core.errors")

# 通用段（1xxxx）
CODE_OK = 0
CODE_VALIDATION_ERROR = 10001  # 参数校验失败
CODE_INTERNAL_ERROR = 10002  # 系统内部错误
CODE_NOT_FOUND = 10003  # 资源不存在
CODE_RATE_LIMITED = 10004  # 请求过于频繁（限流）
# 开放接口/租户/SSO 段（8xxxx）
CODE_TENANT_INVALID = 80001  # 租户标识非法
CODE_TENANT_NOT_FOUND = 80002  # 租户不存在或未注册


class BizError(Exception):
    """业务异常：携带错误码与开发者消息，由全局异常处理器统一响应。"""

    def __init__(self, code: int, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def error_body(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """构造统一错误响应体 {code, message, data}。"""
    return {"code": code, "message": message, "data": data}


async def biz_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """BizError → 统一响应（status_code + 业务错误码）。"""
    _ = request
    error = cast(BizError, exc)
    return JSONResponse(status_code=error.status_code, content=error_body(error.code, error.message))


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Pydantic 参数校验错误 → 400 + 10001（明细放 data.errors）。"""
    _ = request
    error = cast(RequestValidationError, exc)
    return JSONResponse(
        status_code=400,
        content=error_body(CODE_VALIDATION_ERROR, "参数校验失败", {"errors": error.errors()}),
    )


async def http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Starlette/未注册路由错误 → 404 + 10003（其余状态码透传 10003 语义）。"""
    _ = request
    error = cast(StarletteHTTPException, exc)
    return JSONResponse(status_code=error.status_code, content=error_body(CODE_NOT_FOUND, str(error.detail)))


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常 → 500 + 10002，记 ERROR 日志（含 request_id 与路径）。"""
    logger.exception(
        "unhandled exception",
        request_id=get_request_id(),
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(status_code=500, content=error_body(CODE_INTERNAL_ERROR, "系统内部错误"))
