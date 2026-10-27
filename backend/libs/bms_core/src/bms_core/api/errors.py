"""api 层全局异常处理器：业务异常、参数校验与未捕获异常统一转 `ApiResponse`。

**统一渲染单点**（07B `02_05`）：业务异常的状态与文案补全、告警与指标一律经
`build_error_response()`（全局异常处理器与中间件共用），产品码经错误码合并视图
（`error_code_view()`）取 `http_status` 与 `message_key`：

- 视图命中：状态以声明为准（与异常自带值不一致时告警，暴露声明漂移）；异常**显式给了文案**
  仍以显式值为准（既有代码零改动）；
- 视图未命中：**保留异常自带状态与文案**（不兜底 10000/500），记 `ERROR` + 未登记码指标；
- 文案分档：装配真实 translator 时用 `message_key` 取译文，未命中回退 `description` 并告警；
  占位期（`NullTranslator`）直接输出 `message_key`，不告警不计指标（i18n 阶段接入后无需改本层）。
"""

import uuid
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.datastructures import Headers
from starlette.types import Scope

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.context import get_current_request_id
from bms_core.core.exceptions import BizError, DatabaseUnavailableError, InternalError, ParamError
from bms_core.core.logging import get_logger
from bms_core.core.plugin import NULL_PLUGIN_NAME, resolve_plugin
from bms_core.db.health import PrimaryHealth
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.i18n.base import BaseTranslator
from bms_core.metrics.base import BaseMetrics
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import ErrorCodeRecord, error_code_view
from bms_core.tracing.base import TRACE_ID_HEADER

logger = get_logger("bms_core.api.errors")

_REQUEST_ID_HEADER = "X-Request-Id"

METRIC_ERROR_CODE_UNKNOWN = "bms_error_code_unknown_total"
"""渲染时错误码在合并视图中未命中的次数（标签 `code`）。"""

METRIC_ERROR_CODE_UNRESOLVED = "bms_error_code_unresolved_total"
"""真实 translator 下文案缺失（回退 `description`）的次数（标签 `code`）。"""


def _request_id(scope: Scope) -> str:
    """取请求 id（读 `X-Request-Id` → 请求态 request_id → 上下文 → 生成 UUID4）。

    Args:
        scope: ASGI 作用域。

    Returns:
        str: 请求 id。
    """
    state = ConcurrentStableDict(scope.get("state", {}))
    state_id = state.get("request_id")
    header_id = Headers(scope=scope).get(_REQUEST_ID_HEADER)
    request_id = header_id or (str(state_id) if state_id else None) or get_current_request_id()
    return request_id or str(uuid.uuid4())


def _render(status_code: int, body: ApiResponse, scope: Scope) -> JSONResponse:
    """构造统一响应并回写请求 id 与链路 id 头。

    `X-Trace-Id` 从请求态读取（未捕获异常的响应在中间件外层生成，
    上下文已被中间件复位，请求态不受复位影响）。
    """
    state = ConcurrentStableDict(scope.get("state", {}))
    response = JSONResponse(status_code=status_code, content=jsonable_encoder(body))
    response.headers[_REQUEST_ID_HEADER] = _request_id(scope)
    if trace_id := state.get("trace_id"):
        response.headers[TRACE_ID_HEADER] = str(trace_id)
    return response


def _app_state(scope: Scope) -> object | None:
    """取应用状态（非应用上下文——单测裸 scope——返回 None）。

    Args:
        scope: ASGI 作用域。

    Returns:
        object | None: 应用 `state` 对象。
    """
    return getattr(scope.get("app"), "state", None)


def _real_translator(scope: Scope) -> BaseTranslator | None:
    """取真实翻译器（未装配 / 占位 `null` 实现时返回 None）。

    Args:
        scope: ASGI 作用域。

    Returns:
        BaseTranslator | None: 翻译器实例。
    """
    settings = getattr(_app_state(scope), "settings", None)
    provider = str(getattr(getattr(settings, "translator", None), "provider", "") or "").strip()
    if not provider or provider == NULL_PLUGIN_NAME:
        return None
    return cast(
        "BaseTranslator",
        resolve_plugin("translator", provider, expected_version=BaseTranslator.contract_version),
    )


async def _count(scope: Scope, name: str, code: int) -> None:
    """记录错误码相关计数器（未装配指标器时跳过）。

    Args:
        scope: ASGI 作用域。
        name: 指标名。
        code: 错误码（标签值）。
    """
    metrics = cast("BaseMetrics | None", getattr(_app_state(scope), "metrics", None))
    if metrics is None:
        return
    await metrics.counter(name, labels=ConcurrentStableDict({"code": str(code)}))


async def _resolve_message(scope: Scope, record: ErrorCodeRecord) -> str:
    """按视图解析文案（分档：真实 translator 取译文，占位期输出文案键）。

    Args:
        scope: ASGI 作用域。
        record: 命中的错误码定义。

    Returns:
        str: 响应文案（译文 / 文案键 / 回退的描述）。
    """
    translator = _real_translator(scope)
    if translator is None:
        return record.message_key
    locale = translator.resolve_locale(Headers(scope=scope).get("accept-language"))
    try:
        text = await translator.translate(record.message_key, locale=locale)
    except Exception:
        text = ""
    if text and text != record.message_key:
        return text
    logger.warning(
        "error_code_message_missing",
        code=record.code,
        message_key=record.message_key,
        locale=locale,
    )
    await _count(scope, METRIC_ERROR_CODE_UNRESOLVED, record.code)
    return record.description


async def build_error_response(scope: Scope, exc: BizError) -> JSONResponse:
    """构造业务异常的统一错误响应（全局异常处理器与中间件**共用单点**）。

    Args:
        scope: ASGI 作用域（取请求 id / 链路 id / 应用装配）。
        exc: 业务异常。

    Returns:
        JSONResponse: 统一响应（HTTP 状态与业务码分离）。
    """
    record = error_code_view().get(exc.code)
    if record is None:
        logger.error(
            "error_code_unknown",
            code=exc.code,
            path=str(scope.get("path", "")),
            method=str(scope.get("method", "")),
        )
        await _count(scope, METRIC_ERROR_CODE_UNKNOWN, exc.code)
        message = exc.message or f"error.{exc.code}"
        body = ApiResponse(code=exc.code, message=message, data=exc.data)
        return _render(exc.http_status, body, scope)
    if exc.http_status != record.http_status:
        logger.warning(
            "error_code_status_drift",
            code=exc.code,
            declared=record.http_status,
            raised=exc.http_status,
        )
    message = exc.message or await _resolve_message(scope, record)
    body = ApiResponse(code=exc.code, message=message, data=exc.data)
    return _render(record.http_status, body, scope)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。

    Args:
        app: FastAPI 应用实例。
    """

    @app.exception_handler(BizError)
    async def _biz_error_handler(request: Request, exc: BizError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """业务异常 → 统一响应（单点渲染：视图补全状态与文案）。"""
        return await build_error_response(request.scope, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """参数校验失败 → 统一参数异常（10001）。"""
        return await build_error_response(request.scope, ParamError(data=exc.errors()))

    async def _db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """数据库连接类失败 → 标记主库降级并转明确错误（10006 / 503）。"""
        health = getattr(request.app.state, "primary_health", None)
        if isinstance(health, PrimaryHealth):
            health.mark_degraded(PLATFORM_DB_KEY)
        logger.warning(
            "database_unavailable",
            path=request.url.path,
            method=request.method,
            error=type(exc).__name__,
        )
        error = DatabaseUnavailableError("数据库暂不可用，系统已降级为只读模式，写操作被拒绝")
        return await build_error_response(request.scope, error)

    app.add_exception_handler(OperationalError, _db_unavailable_handler)
    app.add_exception_handler(InterfaceError, _db_unavailable_handler)

    @app.exception_handler(Exception)
    async def _uncaught_error_handler(request: Request, exc: Exception) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        """未捕获异常 → 500 统一响应（不暴露堆栈，日志记录完整堆栈）。"""
        state = ConcurrentStableDict(request.scope.get("state", {}))
        fields: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {"path": request.url.path, "method": request.method}
        )
        if trace_id := state.get("trace_id"):
            fields.set("trace_id", trace_id)
        if request_id := state.get("request_id"):
            fields.set("request_id", request_id)
        logger.exception("uncaught_exception", **fields)
        error = InternalError()
        return await build_error_response(request.scope, error)
