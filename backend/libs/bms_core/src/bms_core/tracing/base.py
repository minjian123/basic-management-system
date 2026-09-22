"""链路能力域：调用链 span 上下文契约（真实 OpenTelemetry 接入随分布式与监控阶段回补）。

- `TRACE_ID_HEADER`：入站 / 出站链路 id 请求头（`X-Trace-Id`，透明传递）。
- `new_trace_id` / `new_span_id`：链路 id（32 位 hex）与 span id（16 位 hex）生成；入站中间件与占位链路复用。
- `SpanContext`：span 上下文（frozen：`trace_id` / `span_id` / `parent_span_id` / `name` / `attributes`）。
- `BaseTracer`：能力域中间层契约（`key = "tracer"`）——`span` 为**异步上下文管理器**（进入开启、退出结束，
  与 02-3-6 `BaseDistributedLock.hold` 同款），内部固定编排「取父 span → 开启 → 写上下文变量 → 结束 → 复位」；
  抽象 `start_span` / `end_span` 由实现（真实 / 占位）提供。
- `current_span` / `current_trace_id`：读当前链路上下文（日志体系与业务埋点统一取值入口）。
- `get_tracer`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

上下文变量落点：链路 id / span id 存 `app/core/context.py`（`current_trace_id` / `current_span_id`），
供日志体系（03-2）与审计直接读取；span 对象本身存本域私有变量（`current_span()` 读取）。
键值类型口径：`SpanContext.attributes` 为 `Mapping[str, object]`（贴 OTel `AttributeValue`，允许 int / bool /
float / 字符串序列）；指标标签 `MetricLabels` 为 `Mapping[str, str]`（两域类型不同，回补时按各自规范转换）。
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from bms_core.core.base import BaseObject
from bms_core.core.config import Settings
from bms_core.core.context import (
    get_current_trace_id,
    reset_current_span_id,
    reset_current_trace_id,
    set_current_span_id,
    set_current_trace_id,
)
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin

__all__ = [
    "SPAN_ID_LENGTH",
    "TRACE_ID_HEADER",
    "TRACE_ID_LENGTH",
    "BaseTracer",
    "SpanContext",
    "current_span",
    "current_trace_id",
    "get_tracer",
    "new_span_id",
    "new_trace_id",
]

TRACE_ID_HEADER = "X-Trace-Id"
"""链路 id 请求头（入站读取 / 响应回写 / 出站透传）。"""

TRACE_ID_LENGTH = 32
"""链路 id 长度（32 位 hex，128 位，与 OTel trace id 同形态）。"""

SPAN_ID_LENGTH = 16
"""span id 长度（16 位 hex，64 位，与 OTel span id 同形态）。"""

_current_span: ContextVar[SpanContext | None] = ContextVar("current_span", default=None)


def new_trace_id() -> str:
    """生成链路 id（32 位 hex）。

    Returns:
        str: 链路 id。
    """
    return uuid.uuid4().hex


def new_span_id() -> str:
    """生成 span id（16 位 hex）。

    Returns:
        str: span id。
    """
    return uuid.uuid4().hex[:SPAN_ID_LENGTH]


@dataclass(frozen=True)
class SpanContext(BaseObject):
    """span 上下文：链路 id / span id / 父 span / 名称 / 属性。"""

    trace_id: str
    """链路 id（同一条链路的全部 span 共享）。"""

    span_id: str
    """span id（本次调用段）。"""

    name: str
    """span 名称（如 `http.request`、`db.query`）。"""

    parent_span_id: str | None = None
    """父 span id；链路起点为 None。"""

    attributes: Mapping[str, object] | None = None
    """span 属性（键值，贴 OTel `AttributeValue` 口径）。"""


class BaseTracer(BasePluggable, ABC):
    """链路契约：span 开启 / 结束 + 上下文贯穿。"""

    key: str = "tracer"
    plugin_key: str = "tracer"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        parent: SpanContext | None = None,
    ) -> SpanContext:
        """开启 span。

        Args:
            name: span 名称。
            attributes: span 属性（可选）。
            parent: 父 span 上下文；None 表示链路起点。

        Returns:
            SpanContext: 新 span 上下文。
        """

    @abstractmethod
    async def end_span(self, span: SpanContext) -> None:
        """结束 span（上报或补全耗时）。

        Args:
            span: 待结束的 span 上下文。
        """

    @asynccontextmanager
    async def span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> AsyncGenerator[SpanContext]:
        """span 异步上下文：进入开启、退出结束（异常路径亦保证结束与复位）。

        Args:
            name: span 名称。
            attributes: span 属性（可选）。

        Yields:
            SpanContext: 当前 span 上下文。
        """
        span = await self.start_span(name, attributes=attributes, parent=current_span())
        trace_token = set_current_trace_id(span.trace_id)
        span_token = set_current_span_id(span.span_id)
        span_ctx_token = _current_span.set(span)
        try:
            yield span
        finally:
            await self.end_span(span)
            _current_span.reset(span_ctx_token)
            reset_current_span_id(span_token)
            reset_current_trace_id(trace_token)


def current_span() -> SpanContext | None:
    """当前 span 上下文。

    Returns:
        SpanContext | None: 当前 span；不在 span 内为 None。
    """
    return _current_span.get()


def current_trace_id() -> str | None:
    """当前链路 id（入站中间件或最近的 span 设置）。

    Returns:
        str | None: 链路 id；不在链路内为 None。
    """
    return get_current_trace_id()


def get_tracer(request: Request) -> BaseTracer:
    """取应用级链路器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTracer: 应用装配的链路器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTracer",
        resolve_plugin(
            "tracer",
            settings.tracer.provider,
            expected_version=BaseTracer.contract_version,
        ),
    )
