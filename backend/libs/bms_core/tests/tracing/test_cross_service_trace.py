"""跨服务链路贯通测试（Kiwi 2183）：httpx 出站注入 traceparent → 服务端 span 同 trace。

覆盖 08_02「跨服务调用链可定位」的核心传播语义（08_01 已交付的自动埋点在此验收）：

- `HTTPXClientInstrumentor` 在真实网络传输层（`AsyncHTTPTransport`）出站自动注入 W3C `traceparent`；
- `FastAPIInstrumentor` 以入站 `traceparent` 为父创建服务端 span（同 trace、父链正确）；
- 服务端处理期 `otel_trace_id()` / `resolve_trace_id()` 与 span 上下文一致（日志与 Trace 同 id）。

口径：显式传 `tracer_provider`（独立 provider + in-memory exporter），**不设全局 provider**；被调服务
经后台线程起真实 uvicorn（本地回环，非外部服务）；httpx 埋点为进程级补丁，`finally` 复原保证用例隔离。
"""

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from bms_core.tracing.base import otel_trace_id, resolve_trace_id

_STARTUP_TIMEOUT_S = 5.0


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    """in-memory span 导出器夹具。"""
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> TracerProvider:
    """独立 TracerProvider（显式注入 instrumentor，不设全局）。"""
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
    return tracer_provider


@pytest.fixture
def downstream(provider: TracerProvider) -> Iterator[tuple[int, dict[str, str | None]]]:
    """被调服务：真实 uvicorn（本地回环，后台线程），产出端口与处理期上下文捕获。

    Yields:
        tuple[int, dict[str, str | None]]: `(端口, 处理期链路上下文捕获)`。
    """
    captured: dict[str, str | None] = {}
    app = FastAPI()

    @app.get("/internal/ping")
    async def ping() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        """被调服务端点：记录处理期链路上下文（模拟日志取值）。"""
        captured["otel"] = otel_trace_id()
        captured["resolved"] = resolve_trace_id()
        return {"status": "ok"}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn 未在超时内就绪"
    try:
        yield port, captured
    finally:
        server.should_exit = True
        thread.join(timeout=_STARTUP_TIMEOUT_S)


def _trace_id_of(span: object) -> str:
    """取 span / span 上下文的 32 位 hex trace id。"""
    context = getattr(span, "context", span)
    trace_id = getattr(context, "trace_id", None)
    assert trace_id is not None
    return format(trace_id, "032x")


def _span_id_of(span: object) -> str:
    """取 span / span 上下文的 16 位 hex span id。"""
    context = getattr(span, "context", span)
    span_id = getattr(context, "span_id", None)
    assert span_id is not None
    return format(span_id, "016x")


@pytest.mark.kiwi_id(2183)
async def test_cross_service_trace_propagation(
    provider: TracerProvider, exporter: InMemorySpanExporter, downstream: tuple[int, dict[str, str | None]]
) -> None:
    """客户端与服务端 span 同 trace、父链正确；服务端上下文 id 与 span 一致。"""
    port, captured = downstream
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            response = await client.get("/internal/ping")
        assert response.status_code == 200
    finally:
        HTTPXClientInstrumentor().uninstrument()

    spans = exporter.get_finished_spans()
    client_spans = [span for span in spans if span.kind == SpanKind.CLIENT]
    server_spans = [span for span in spans if span.kind == SpanKind.SERVER]
    assert client_spans, [span.name for span in spans]
    assert server_spans, [span.name for span in spans]

    client_span, server_span = client_spans[0], server_spans[0]
    assert _trace_id_of(server_span) == _trace_id_of(client_span)
    assert server_span.parent is not None
    assert _span_id_of(server_span.parent) == _span_id_of(client_span)
    # 服务端处理期日志链路 id 与 OTel span 同源（OTel 为事实源）
    expected = _trace_id_of(server_span)
    assert captured["otel"] == expected
    assert captured["resolved"] == expected
