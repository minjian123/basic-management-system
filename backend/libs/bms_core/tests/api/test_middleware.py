"""入站链路 id 中间件测试（Kiwi 44 生成 / 回显 / 上下文贯穿 / 复位；Kiwi 63 request_id 兜底）。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from bms_core.api.middleware import TraceIdMiddleware
from bms_core.core.context import (
    get_current_trace_id,
    reset_current_request_id,
    reset_current_trace_id,
    set_current_request_id,
    set_current_trace_id,
)
from bms_core.tracing.base import TRACE_ID_HEADER, TRACE_ID_LENGTH


def _build_app() -> FastAPI:
    """构造带链路 id 中间件的测试应用（接口回显当前链路 id）。"""
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/whoami")
    async def whoami() -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]
        return {"trace_id": get_current_trace_id()}

    return app


@pytest.mark.kiwi_id(44)
async def test_generates_trace_id_and_propagates_context() -> None:
    """无入站头时生成链路 id：响应头回写 32 位 hex，且接口内上下文可见同一值。"""
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami")

    generated = resp.headers[TRACE_ID_HEADER]
    assert len(generated) == TRACE_ID_LENGTH
    assert resp.json() == {"trace_id": generated}


@pytest.mark.kiwi_id(44)
async def test_echoes_inbound_trace_id() -> None:
    """带入站链路 id 时原样沿用并回写（跨实例透传口径）。"""
    inbound = "b" * TRACE_ID_LENGTH
    async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
        resp = await client.get("/whoami", headers={TRACE_ID_HEADER: inbound})

    assert resp.headers[TRACE_ID_HEADER] == inbound
    assert resp.json() == {"trace_id": inbound}


@pytest.mark.kiwi_id(44)
async def test_resets_and_restores_previous_context() -> None:
    """请求结束复位到中间件之前的值，且各请求链路 id 相互独立。"""
    app = _build_app()
    outer = "c" * TRACE_ID_LENGTH
    token = set_current_trace_id(outer)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/whoami")
            second = await client.get("/whoami")
        first_trace = first.headers[TRACE_ID_HEADER]
        second_trace = second.headers[TRACE_ID_HEADER]
    finally:
        reset_current_trace_id(token)

    assert first_trace != second_trace
    assert first_trace != outer
    assert get_current_trace_id() is None


@pytest.mark.kiwi_id(63)
async def test_falls_back_to_request_id() -> None:
    """上下文已有 request_id（请求日志中间件先设）时，trace_id 取其兜底。"""
    request_id = "r" * TRACE_ID_LENGTH
    token = set_current_request_id(request_id)
    try:
        async with AsyncClient(transport=ASGITransport(app=_build_app()), base_url="http://test") as client:
            resp = await client.get("/whoami")
    finally:
        reset_current_request_id(token)

    assert resp.headers[TRACE_ID_HEADER] == request_id
    assert resp.json() == {"trace_id": request_id}


@pytest.mark.kiwi_id(44)
async def test_non_http_scope_passthrough() -> None:
    """非 HTTP 作用域（lifespan 等）直通：下游照常执行、不进链路上下文。"""
    sent: list[str] = []

    async def downstream(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        await send({"type": "lifespan.startup.complete"})

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        sent.append(str(message["type"]))

    await TraceIdMiddleware(downstream)({"type": "lifespan"}, receive, send)
    assert sent == ["lifespan.startup.complete"]
    assert get_current_trace_id() is None
