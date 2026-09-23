"""tracing 能力域真实接入装配：全局 TracerProvider 配置与程序化自动埋点。

- `configure_tracing`：按 `[tracer]` 配置构造全局 `TracerProvider`（资源标签 `service.name` /
  `service.version`、采样器、OTLP/HTTP 导出、W3C 传播）；**幂等**（进程内只配置一次，重复调用复用）。
- `instrument_observability`：程序化自动埋点——FastAPI（服务端 span，排除探针 / 指标端点）、
  SQLAlchemy（全局补丁，覆盖惰性创建的租户引擎）、Redis、httpx（出站自动注入 `traceparent`，跨服务贯通）、
  Celery（当前无运行时，接入即生效）；单项失败降级、不阻断启动。
- `setup_observability`：服务工厂装配入口（配置 provider + 埋点 + 注册 provider 释放）。
- `TracerProviderResource`：把 `TracerProvider` 纳入应用资源生命周期（关闭时 flush + shutdown）。

口径：OTel 为链路 id 唯一事实源（`bms_core.tracing.base.resolve_trace_id`）；导出失败只记 SDK 日志、
不影响业务（collector 未部署时应用照常运行）。
"""

from collections.abc import Mapping
from importlib import import_module
from typing import Any, cast

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.config import Settings
from bms_core.core.logging import get_logger

__all__ = [
    "TracerProviderResource",
    "configure_tracing",
    "instrument_observability",
    "setup_observability",
]

_LOGGER = "bms_core.tracing"
_EXCLUDED_URLS = "/healthz,/readyz,/metrics"
"""FastAPI 埋点排除路径（探针与指标端点，避免噪声）。"""

_configured = False
"""进程内一次性配置标记（`set_tracer_provider` 只允许设置一次真实 provider）。"""


class TracerProviderResource(BaseAsyncResource):
    """`TracerProvider` 生命周期包装：应用关闭时 flush 并释放后台导出。"""

    def __init__(self, provider: TracerProvider) -> None:
        """初始化。

        Args:
            provider: 已配置的全局 TracerProvider。
        """
        self._provider = provider

    async def aclose(self) -> None:
        """释放（幂等）：`shutdown()` flush 未导出 span 并停止批处理线程。"""
        self._provider.shutdown()


def configure_tracing(settings: Settings, identity: object | None = None) -> TracerProvider | None:
    """配置全局 OTel `TracerProvider`（幂等；`provider != otel` 时跳过）。

    Args:
        settings: 应用配置（取 `[tracer]` 端点 / 采样 / 超时）。
        identity: 服务身份（`ServiceIdentity`；提供 `service.name` / `service.version` 资源标签）。

    Returns:
        TracerProvider | None: 本次新建的 provider；跳过或已配置时为 None。
    """
    global _configured
    if settings.tracer.provider != "otel" or _configured:
        return None
    name = str(getattr(identity, "name", "") or settings.app.service or "bms")
    version = str(getattr(identity, "version", "") or "")
    resource = Resource.create({SERVICE_NAME: name, SERVICE_VERSION: version})
    provider = TracerProvider(resource=resource, sampler=_build_sampler(settings))
    exporter = OTLPSpanExporter(
        endpoint=_traces_endpoint(settings.tracer.otlp_endpoint),
        timeout=settings.tracer.export_timeout_ms / 1000,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    set_global_textmap(TraceContextTextMapPropagator())
    _configured = True
    get_logger(_LOGGER).info(
        "tracing_configured",
        service=name,
        version=version,
        endpoint=settings.tracer.otlp_endpoint,
        sampler=settings.tracer.sampler,
        sampler_ratio=settings.tracer.sampler_ratio,
    )
    return provider


def instrument_observability(app: FastAPI, settings: Settings) -> None:
    """程序化自动埋点（`provider == otel` 时生效；单项失败降级不阻断启动）。

    Args:
        app: 应用实例（FastAPI 服务端 span 埋点目标）。
        settings: 应用配置（能力选择）。
    """
    if settings.tracer.provider != "otel":
        return
    _instrument("fastapi", lambda: _instrument_fastapi(app))
    _instrument("sqlalchemy", _instrument_sqlalchemy)
    _instrument("redis", _instrument_redis)
    _instrument("httpx", _instrument_httpx)
    _instrument("celery", _instrument_celery)


def setup_observability(app: FastAPI, settings: Settings) -> None:
    """服务工厂装配入口：配置 provider（+ 释放登记）并自动埋点。

    Args:
        app: 应用实例。
        settings: 应用配置。
    """
    provider = configure_tracing(settings, getattr(app.state, "service_identity", None))
    if provider is not None:
        resources = getattr(app.state, "resources", None)
        if resources is not None:
            resources.register(TracerProviderResource(provider))
    instrument_observability(app, settings)


def _build_sampler(settings: Settings) -> Any:
    """按 `[tracer]` 配置构造采样器，失败回退缺省（父级比例采样）。

    Args:
        settings: 应用配置。

    Returns:
        Any: OTel `Sampler`。
    """
    ratio = settings.tracer.sampler_ratio
    mapping: Mapping[str, Any] = {
        "always_on": ALWAYS_ON,
        "always_off": ALWAYS_OFF,
        "traceidratio": TraceIdRatioBased(ratio),
        "parentbased_always_on": ParentBased(ALWAYS_ON),
        "parentbased_traceidratio": ParentBased(TraceIdRatioBased(ratio)),
    }
    sampler = mapping.get(settings.tracer.sampler)
    if sampler is None:
        get_logger(_LOGGER).warning("tracer_sampler_unknown", sampler=settings.tracer.sampler)
        return ParentBased(TraceIdRatioBased(ratio))
    return sampler


def _traces_endpoint(base: str) -> str:
    """把 OTLP 基址补全为 traces 采集端点（HTTP 导出器要求完整路径）。

    Args:
        base: 基址（如 `http://localhost:4318`）。

    Returns:
        str: 完整端点（`.../v1/traces`）。
    """
    base = base.rstrip("/")
    return base if base.endswith("/v1/traces") else f"{base}/v1/traces"


def _instrument(label: str, apply: Any) -> None:
    """执行单类埋点并降级（缺插件 / 已埋点异常只记日志，不阻断启动）。

    Args:
        label: 埋点标识（日志用）。
        apply: 零参埋点可调用。
    """
    try:
        apply()
    except Exception as exc:  # 缺插件 / 版本不兼容等：降级
        get_logger(_LOGGER).warning("instrumentation_skipped", target=label, detail=repr(exc))


def _instrument_fastapi(app: FastAPI) -> None:
    """FastAPI 服务端埋点（排除探针与指标端点）。"""
    module = cast("Any", import_module("opentelemetry.instrumentation.fastapi"))
    module.FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)


def _instrument_sqlalchemy() -> None:
    """SQLAlchemy 全局埋点（补丁 `create_engine` / `create_async_engine`，覆盖惰性租户引擎）。"""
    module = cast("Any", import_module("opentelemetry.instrumentation.sqlalchemy"))
    module.SQLAlchemyInstrumentor().instrument()


def _instrument_redis() -> None:
    """Redis 客户端埋点。"""
    from opentelemetry.instrumentation.redis import RedisInstrumentor

    RedisInstrumentor().instrument()  # pyright: ignore[reportUnknownMemberType]


def _instrument_httpx() -> None:
    """httpx 出站埋点（自动注入 `traceparent`，跨服务贯通）。"""
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()


def _instrument_celery() -> None:
    """Celery 埋点（当前无运行时；待任务调度阶段引入 Celery 后生效）。"""
    module = cast("Any", import_module("opentelemetry.instrumentation.celery"))
    module.CeleryInstrumentor().instrument()
