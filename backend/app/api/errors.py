"""api 层全局异常处理器：业务异常、参数校验与未捕获异常统一转 `ApiResponse`。"""

import uuid
from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.context import get_current_request_id
from app.core.exceptions import BizError, InternalError, ParamError
from app.core.logging import get_logger
from app.schemas.common import ApiResponse
from app.tracing.base import TRACE_ID_HEADER

logger = get_logger("app.api.errors")

_REQUEST_ID_HEADER = "X-Request-Id"


def _request_id(request: Request) -> str:
    """取请求 id（读 `X-Request-Id` → 请求态 request_id → 上下文 → 生成 UUID4）。

    Args:
        request: 请求对象。

    Returns:
        str: 请求 id。
    """
    state: Mapping[str, object] = request.scope.get("state", {})
    state_id = state.get("request_id")
    header_id = request.headers.get(_REQUEST_ID_HEADER)
    request_id = header_id or (str(state_id) if state_id else None) or get_current_request_id()
    return request_id or str(uuid.uuid4())


def _respond(status_code: int, body: ApiResponse, request: Request) -> JSONResponse:
    """构造统一响应并回写请求 id 与链路 id 头。

    `X-Trace-Id` 从请求态读取（未捕获异常的响应在中间件外层生成，
    上下文已被中间件复位，请求态不受复位影响）。
    """
    state: Mapping[str, object] = request.scope.get("state", {})
    response = JSONResponse(status_code=status_code, content=jsonable_encoder(body))
    response.headers[_REQUEST_ID_HEADER] = _request_id(request)
    if trace_id := state.get("trace_id"):
        response.headers[TRACE_ID_HEADER] = str(trace_id)
    return response


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。

    Args:
        app: FastAPI 应用实例。
    """

    @app.exception_handler(BizError)
    async def _biz_error_handler(request: Request, exc: BizError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """业务异常 → 统一响应（HTTP 状态与业务码分离）。"""
        body = ApiResponse(code=exc.code, message=exc.message or f"error.{exc.code}", data=exc.data)
        return _respond(exc.http_status, body, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """参数校验失败 → 统一参数异常（10001）。"""
        error = ParamError(data=exc.errors())
        body = ApiResponse(code=error.code, message=error.message or f"error.{error.code}", data=error.data)
        return _respond(error.http_status, body, request)

    @app.exception_handler(Exception)
    async def _uncaught_error_handler(request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """未捕获异常 → 500 统一响应（不暴露堆栈，日志记录完整堆栈）。"""
        state: Mapping[str, object] = request.scope.get("state", {})
        fields: dict[str, object] = {"path": request.url.path, "method": request.method}
        if trace_id := state.get("trace_id"):
            fields["trace_id"] = trace_id
        if request_id := state.get("request_id"):
            fields["request_id"] = request_id
        logger.exception("uncaught_exception", **fields)
        error = InternalError()
        body = ApiResponse(code=error.code, message=f"error.{error.code}", data=None)
        return _respond(error.http_status, body, request)
