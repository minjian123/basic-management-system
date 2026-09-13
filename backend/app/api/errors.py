"""api 层全局异常处理器：业务异常、参数校验与未捕获异常统一转 `ApiResponse`。"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import BizError, InternalError, ParamError
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

_REQUEST_ID_HEADER = "X-Request-Id"


def _request_id(request: Request) -> str:
    """取请求 id（读 `X-Request-Id`，缺失生成 UUID4）。

    Args:
        request: 请求对象。

    Returns:
        str: 请求 id。
    """
    return request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())


def _respond(status_code: int, body: ApiResponse, request_id: str) -> JSONResponse:
    """构造统一响应并回写请求 id 头。"""
    response = JSONResponse(status_code=status_code, content=jsonable_encoder(body))
    response.headers[_REQUEST_ID_HEADER] = request_id
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
        return _respond(exc.http_status, body, _request_id(request))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """参数校验失败 → 统一参数异常（10001）。"""
        error = ParamError(data=exc.errors())
        body = ApiResponse(code=error.code, message=error.message or f"error.{error.code}", data=error.data)
        return _respond(error.http_status, body, _request_id(request))

    @app.exception_handler(Exception)
    async def _uncaught_error_handler(request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """未捕获异常 → 500 统一响应（不暴露堆栈，日志记录完整堆栈）。"""
        request_id = _request_id(request)
        logger.exception("未捕获异常 request_id=%s", request_id)
        error = InternalError()
        body = ApiResponse(code=error.code, message=f"error.{error.code}", data=None)
        return _respond(error.http_status, body, request_id)
