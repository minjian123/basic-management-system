"""tracing 能力域真实实现：OpenTelemetry（`opentelemetry-sdk`）。

- `OtelTracer`：`BaseTracer` 真实实现（provider `otel`）——`start_span` / `end_span` 落到 OTel 全局
  `TracerProvider`（由 `bms_core.tracing.setup.configure_tracing` 配置），span id 即 OTel 的 32/16 位 hex，
  使日志 `trace_id` 与 Tempo 的 trace id 一致；进入 / 退出时 `attach` / `detach` OTel 上下文，令自动埋点
  span 与手工 span 在同一上下文内正确挂父链。
- **降级**：全局 provider 未配置（占位 / 测试环境未开启 OTel）时，OTel span 上下文无效——退回本地
  生成 `uuid4` 形态 id 并维护父子链（与 `NullTracer` 同口径），保证链路贯穿不因未开启而丢失。

口径：OTel 为链路 id **唯一事实源**（`resolve_trace_id`）；跨进程经 W3C `traceparent` 传播（httpx 自动埋点）。
"""

from collections.abc import Mapping
from contextlib import suppress
from typing import Any, cast

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, TraceFlags
from opentelemetry.trace import SpanContext as OtelSpanContext

from bms_core.core.context import get_current_trace_id
from bms_core.tracing.base import BaseTracer, SpanContext, new_span_id, new_trace_id

__all__ = [
    "OtelTracer",
]


class OtelTracer(BaseTracer):
    """OpenTelemetry 链路实现：span 落到全局 `TracerProvider`，经 collector 上报 Tempo。"""

    plugin_name = "otel"

    def __init__(self, tracer_name: str = "bms", *, tracer: Any | None = None) -> None:
        """初始化。

        Args:
            tracer_name: OTel tracer 名（用于区分埋点来源；未显式注入 tracer 时生效）。
            tracer: 显式注入的 OTel `Tracer`（测试用独立 provider；缺省取全局 tracer）。
        """
        self._tracer: Any = tracer if tracer is not None else trace.get_tracer(tracer_name)
        self._active: dict[str, tuple[Any, object]] = {}

    async def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        parent: SpanContext | None = None,
    ) -> SpanContext:
        """开启 OTel span（无有效 provider 时退回本地占位 id）。

        Args:
            name: span 名称。
            attributes: span 属性（可选）。
            parent: 父 span 上下文（无活动 OTel 上下文时用于构造远端父）。

        Returns:
            SpanContext: 与 OTel span 一致的上下文（降级时为本地产物）。
        """
        context = _parent_context(parent)
        otel_span = self._tracer.start_span(name, context=context, attributes=cast("Any", attributes))
        span_context: Any = otel_span.get_span_context()
        # 无有效 provider 时 OTel 返回 NonRecordingSpan（上下文无效，或仅透传父上下文）：
        # 退回本地占位 id，保持父子链与上下文贯穿（与 NullTracer 同口径）。
        if not span_context.is_valid or isinstance(otel_span, NonRecordingSpan):
            return _local_span(name, attributes, parent)
        span_id = format(span_context.span_id, "016x")
        otel_parent: Any = getattr(otel_span, "parent", None)
        token = otel_context.attach(trace.set_span_in_context(otel_span))
        self._active[span_id] = (otel_span, token)
        return SpanContext(
            trace_id=format(span_context.trace_id, "032x"),
            span_id=span_id,
            name=name,
            parent_span_id=format(otel_parent.span_id, "016x") if otel_parent is not None else None,
            attributes=attributes,
        )

    async def end_span(self, span: SpanContext) -> None:
        """结束 OTel span 并复位上下文。

        Args:
            span: 待结束的 span 上下文（本实现开启的 span；未知 span 忽略）。
        """
        entry = self._active.pop(span.span_id, None)
        if entry is None:
            return
        otel_span, token = entry
        try:
            otel_span.end()
        finally:
            with suppress(Exception):
                otel_context.detach(cast("Any", token))


def _parent_context(parent: SpanContext | None) -> Any:
    """构造显式父上下文（仅当无有效活动 OTel span 且给定父 span 时）。

    Args:
        parent: 本域父 span 上下文。

    Returns:
        Any: OTel `Context`（远端父）或 None（走活动上下文自动挂父）。
    """
    current = trace.get_current_span().get_span_context()
    if getattr(current, "is_valid", False):
        return None
    if parent is None or not parent.trace_id or not parent.span_id:
        return None
    remote = OtelSpanContext(
        trace_id=int(parent.trace_id, 16),
        span_id=int(parent.span_id, 16),
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    return trace.set_span_in_context(NonRecordingSpan(remote))


def _local_span(
    name: str,
    attributes: Mapping[str, object] | None,
    parent: SpanContext | None,
) -> SpanContext:
    """无有效 OTel provider 时生成本地占位 span（保持父子链与上下文贯穿）。

    Args:
        name: span 名称。
        attributes: span 属性。
        parent: 父 span 上下文。

    Returns:
        SpanContext: 本地占位 span 上下文。
    """
    trace_id = parent.trace_id if parent is not None else (get_current_trace_id() or new_trace_id())
    return SpanContext(
        trace_id=trace_id,
        span_id=new_span_id(),
        name=name,
        parent_span_id=parent.span_id if parent is not None else None,
        attributes=attributes,
    )
