"""链路基座契约测试（Kiwi 44）：继承 / 常量 / 占位 span 与父链 / 上下文贯穿 / 异常复位 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_tracer
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.core.context import (
    get_current_span_id,
    get_current_trace_id,
    reset_current_trace_id,
    set_current_trace_id,
)
from app.main import create_app, lifespan
from app.tracing.base import (
    SPAN_ID_LENGTH,
    TRACE_ID_HEADER,
    TRACE_ID_LENGTH,
    BaseTracer,
    current_span,
    current_trace_id,
    new_span_id,
    new_trace_id,
)
from app.tracing.null import NullTracer


class BoomError(RuntimeError):
    """测试用异常（验证异常路径复位）。"""


@pytest.mark.kiwi_id(44)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseTracer, BaseCapability)
    assert issubclass(NullTracer, BaseTracer)
    assert issubclass(NullTracer, BaseNullObject)
    assert BaseTracer.key == "tracer"

    tracer = NullTracer()
    assert tracer.placeholder is True
    assert "占位实现" in tracer.describe()


@pytest.mark.kiwi_id(44)
def test_constants_and_id_generators() -> None:
    """请求头常量与 id 生成口径（trace 32 位 hex / span 16 位 hex，且不重复）。"""
    assert TRACE_ID_HEADER == "X-Trace-Id"
    assert (TRACE_ID_LENGTH, SPAN_ID_LENGTH) == (32, 16)

    trace_id = new_trace_id()
    span_id = new_span_id()
    assert len(trace_id) == TRACE_ID_LENGTH
    assert len(span_id) == SPAN_ID_LENGTH
    assert new_trace_id() != trace_id
    assert new_span_id() != span_id


@pytest.mark.kiwi_id(44)
async def test_span_chain_and_context() -> None:
    """占位 span：起点新建链路、嵌套继承链路并记父 span，上下文贯穿且退出复位。"""
    tracer = NullTracer()
    assert current_span() is None
    assert current_trace_id() is None

    async with tracer.span("http.request", attributes={"route": "/api/v1/users"}) as outer:
        assert len(outer.trace_id) == TRACE_ID_LENGTH
        assert outer.parent_span_id is None
        assert outer.attributes == {"route": "/api/v1/users"}
        assert current_span() is outer
        assert get_current_trace_id() == outer.trace_id
        assert get_current_span_id() == outer.span_id

        async with tracer.span("db.query") as inner:
            assert inner.trace_id == outer.trace_id
            assert inner.parent_span_id == outer.span_id
            assert inner.span_id != outer.span_id
            assert current_span() is inner
            assert get_current_span_id() == inner.span_id

        assert current_span() is outer
        assert get_current_span_id() == outer.span_id

    assert current_span() is None
    assert current_trace_id() is None
    assert get_current_trace_id() is None
    assert get_current_span_id() is None


@pytest.mark.kiwi_id(44)
async def test_span_reuses_inbound_trace_id() -> None:
    """占位 span 复用入站中间件写入的链路 id（链路 id 不被新建覆盖）。"""
    tracer = NullTracer()
    inbound = "a" * TRACE_ID_LENGTH
    token = set_current_trace_id(inbound)
    try:
        async with tracer.span("job.run") as span:
            assert span.trace_id == inbound
    finally:
        reset_current_trace_id(token)


@pytest.mark.kiwi_id(44)
async def test_span_resets_on_exception() -> None:
    """异常路径下 span 仍结束并复位上下文（不泄漏到后续调用）。"""
    tracer = NullTracer()
    with pytest.raises(BoomError):
        async with tracer.span("http.request"):
            raise BoomError
    assert current_span() is None
    assert current_trace_id() is None


@pytest.mark.kiwi_id(44)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位链路器；接口内 span 起的链路 id 与响应头一致。"""
    app = create_app()
    async with lifespan(app):
        assert isinstance(app.state.tracer, NullTracer)

        @app.get("/trace-probe")
        async def trace_probe(  # pyright: ignore[reportUnusedFunction]
            tracer: Annotated[BaseTracer, Depends(get_tracer)],
        ) -> dict[str, object]:
            async with tracer.span("http.request"):
                return {"key": tracer.key, "trace_id": current_trace_id()}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.get("/trace-probe")

        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == "tracer"
        assert body["trace_id"] == resp.headers[TRACE_ID_HEADER]
