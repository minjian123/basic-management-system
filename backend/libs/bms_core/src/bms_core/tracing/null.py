"""tracing 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.tracing.base.py 迁入）。"""

from collections.abc import Mapping

from bms_core.core.capability import BaseNullObject
from bms_core.core.context import get_current_trace_id
from bms_core.tracing.base import BaseTracer, SpanContext, new_span_id, new_trace_id

__all__ = [
    "NullTracer",
]


class NullTracer(BaseTracer, BaseNullObject):
    """占位链路：生成真实形态占位 ID 与父子链、维护上下文变量，**不上报**（不连 OTel）。"""

    async def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        parent: SpanContext | None = None,
    ) -> SpanContext:
        """开启占位 span。

        链路 id 取值顺序：父 span 的链路 id → 当前上下文链路 id（入站中间件设置）→ 新生成；
        span id 每次新生成（16 位 hex）。

        Args:
            name: span 名称。
            attributes: span 属性（占位仅随上下文携带）。
            parent: 父 span 上下文。

        Returns:
            SpanContext: 占位 span 上下文。
        """
        trace_id = parent.trace_id if parent is not None else (get_current_trace_id() or new_trace_id())
        return SpanContext(
            trace_id=trace_id,
            span_id=new_span_id(),
            name=name,
            parent_span_id=parent.span_id if parent is not None else None,
            attributes=attributes,
        )

    async def end_span(self, span: SpanContext) -> None:
        """空操作（占位不上报）。

        Args:
            span: 待结束的 span 上下文（占位忽略）。
        """
