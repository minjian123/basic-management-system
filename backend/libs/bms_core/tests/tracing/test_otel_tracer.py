"""OpenTelemetry 链路真实实现测试（Kiwi 2182）：span 记录 / 上下文贯穿 / 父链 / 降级。"""

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NoOpTracer

from bms_core.core.context import get_current_span_id, get_current_trace_id
from bms_core.tracing.base import BaseTracer, otel_trace_id, resolve_trace_id
from bms_core.tracing.otel import OtelTracer


def _trace_id_of(span: object) -> str:
    """取已结束 span 的 trace id（类型收窄：`span.context` 声明为可选）。

    Args:
        span: 已结束的 span。

    Returns:
        str: 32 位 hex trace id。
    """
    context = getattr(span, "context", None)
    assert context is not None
    return format(context.trace_id, "032x")


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    """in-memory span 导出器夹具（断言已结束 span）。"""
    return InMemorySpanExporter()


@pytest.fixture
def tracer(exporter: InMemorySpanExporter) -> Iterator[OtelTracer]:
    """以独立 provider 注入的 OTel 链路实现夹具。"""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield OtelTracer(tracer=provider.get_tracer("test"))


@pytest.mark.kiwi_id(2182)
def test_contract_and_provider() -> None:
    """真实实现继承链路契约、provider 为 otel。"""
    assert issubclass(OtelTracer, BaseTracer)
    assert OtelTracer.plugin_name == "otel"
    assert OtelTracer.key == "tracer"


@pytest.mark.kiwi_id(2182)
async def test_span_ids_and_context(tracer: OtelTracer, exporter: InMemorySpanExporter) -> None:
    """span 返回 OTel 形态 id，进入时上下文变量与 OTel trace id 一致。"""
    async with tracer.span("outer"):
        inside_trace = get_current_trace_id()
        inside_span = get_current_span_id()
        assert inside_trace is not None and len(inside_trace) == 32
        assert inside_span is not None and len(inside_span) == 16
        assert resolve_trace_id() == inside_trace
        assert otel_trace_id() == inside_trace

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["outer"]
    assert _trace_id_of(spans[0]) == inside_trace
    # 退出后复位
    assert get_current_trace_id() is None
    assert get_current_span_id() is None


@pytest.mark.kiwi_id(2182)
async def test_nested_parent_chain(tracer: OtelTracer, exporter: InMemorySpanExporter) -> None:
    """嵌套 span 共享 trace id 且记录父 span id。"""
    async with tracer.span("outer"):
        outer_span = get_current_span_id()
        async with tracer.span("inner"):
            assert resolve_trace_id() is not None

    by_name = {span.name: span for span in exporter.get_finished_spans()}
    inner = by_name["inner"]
    assert _trace_id_of(inner) == _trace_id_of(by_name["outer"])
    assert inner.parent is not None
    assert format(inner.parent.span_id, "016x") == outer_span


@pytest.mark.kiwi_id(2182)
async def test_fallback_without_provider() -> None:
    """无有效 provider（NoOp）时退回本地占位 id，链路贯穿不丢失、父子链保留。"""
    tracer = OtelTracer(tracer=NoOpTracer())
    async with tracer.span("root") as root:
        assert len(root.trace_id) == 32 and len(root.span_id) == 16
        assert root.trace_id != "0" * 32
        async with tracer.span("child") as child:
            assert child.trace_id == root.trace_id
            assert child.parent_span_id == root.span_id
            assert get_current_trace_id() == root.trace_id
