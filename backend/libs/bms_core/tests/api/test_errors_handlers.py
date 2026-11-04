"""全局异常处理器：参数校验与未捕获异常的统一渲染（msg 任务 `01-1-1` 补测；Kiwi 2411）。

补的是 `register_exception_handlers()` 内两个闭包的**执行路径**：`RequestValidationError` → `10001`；
未捕获异常 → `10000` / 500 且回写请求 id 与链路 id（含两 id 缺失时的兜底）。这两条路径此前只在
集成档（CI 跳过的 65 例）下跑到，模块级覆盖率因本次改动（`build_error_response` 首步加产品码覆盖）
被纳入门禁而暴露缺口。
"""

import json
from collections.abc import Awaitable, Callable
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Scope

from bms_core.api.errors import register_exception_handlers
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import ErrorCode
from bms_core.services.module_registry import error_code_view

pytestmark = pytest.mark.kiwi_id(2411)

_REQUEST_ID_HEADER = "X-Request-Id"
_TRACE_ID_HEADER = "X-Trace-Id"

_Handler = Callable[[Request, BaseException], Awaitable[JSONResponse]]
"""异常处理器签名（`register_exception_handlers` 注册的闭包）。"""


def _app() -> FastAPI:
    """构造仅注册全局异常处理器的应用。

    Returns:
        FastAPI: 应用实例。
    """
    app = FastAPI()
    register_exception_handlers(app)
    return app


def _request(*, trace_id: str | None = None, request_id: str | None = None) -> Request:
    """构造带可选链路 / 请求 id 的请求。

    Args:
        trace_id: 请求态链路 id。
        request_id: 请求态请求 id。

    Returns:
        Request: 请求对象。
    """
    state: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    if trace_id is not None:
        state.set("trace_id", trace_id)
    if request_id is not None:
        state.set("request_id", request_id)
    scope: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/demos",
            "query_string": b"",
            "headers": [],
            "state": state,
        }
    )
    return Request(cast("Scope", scope))


def _body(response: JSONResponse) -> ConcurrentStableDict[str, object]:
    """解析响应体。

    Args:
        response: 统一响应。

    Returns:
        ConcurrentStableDict[str, object]: 响应 JSON。
    """
    return ConcurrentStableDict(cast("dict[str, object]", json.loads(bytes(response.body))))


def _handler(app: FastAPI, exc_type: type[BaseException]) -> _Handler:
    """取注册的异常处理器。

    Args:
        app: 应用实例。
        exc_type: 异常类型。

    Returns:
        _Handler: 处理器（`async (request, exc) -> JSONResponse`）。
    """
    return cast("_Handler", app.exception_handlers[exc_type])


async def test_validation_error_maps_to_param_code() -> None:
    """参数校验失败：统一转 `10001`，状态取登记值，`data` 携带 FastAPI 诊断。"""
    handler = _handler(_app(), RequestValidationError)
    errors = [{"loc": ("body", "name"), "msg": "Field required", "type": "missing"}]
    response = await handler(_request(), RequestValidationError(errors))
    record = error_code_view().get(int(ErrorCode.PARAM))
    assert record is not None
    body = _body(response)
    assert (response.status_code, body["code"]) == (record.http_status, int(ErrorCode.PARAM))
    # 经 JSON 渲染后 `loc` 由元组变数组，按序列化后的形态比较。
    assert body["data"] == json.loads(json.dumps(errors))


async def test_uncaught_error_maps_to_internal_and_echoes_ids() -> None:
    """未捕获异常：`10000` / 500，并回写请求态里的请求 id 与链路 id（不暴露堆栈）。"""
    handler = _handler(_app(), Exception)
    response = await handler(_request(trace_id="t-1", request_id="r-1"), RuntimeError("boom"))
    body = _body(response)
    assert (response.status_code, body["code"]) == (500, int(ErrorCode.INTERNAL))
    assert response.headers[_REQUEST_ID_HEADER] == "r-1"
    assert response.headers[_TRACE_ID_HEADER] == "t-1"
    assert "boom" not in str(body)


async def test_uncaught_error_without_ids_generates_request_id() -> None:
    """两个 id 都缺失：仍返回 `10000`，请求 id 兜底生成（链路 id 不写）。"""
    handler = _handler(_app(), Exception)
    response = await handler(_request(), RuntimeError("boom"))
    assert _body(response)["code"] == int(ErrorCode.INTERNAL)
    assert response.headers[_REQUEST_ID_HEADER]
    assert _TRACE_ID_HEADER not in response.headers
