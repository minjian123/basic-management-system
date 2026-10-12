"""可观测装配用例（Kiwi 2182）：TracerProvider 配置 / 自动埋点目标 / 装配入口 / 采样与端点解析。

口径：真实 provider 只在配置用例内建立并在末尾 `shutdown()` 释放（不向采集端导出）；埋点目标逐项真实执行
后立即 `uninstrument()` 还原全局补丁，避免污染其他用例；celery 埋点模块依赖缺失，以替换导入覆盖装配分支。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry.instrumentation.redis import RedisInstrumentor  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # pyright: ignore[reportMissingTypeStubs]
from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ParentBased

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.tracing import setup
from bms_core.tracing.setup import (
    TracerProviderResource,
    _build_sampler,  # pyright: ignore[reportPrivateUsage]
    _instrument,  # pyright: ignore[reportPrivateUsage]
    _instrument_celery,  # pyright: ignore[reportPrivateUsage]
    _instrument_fastapi,  # pyright: ignore[reportPrivateUsage]
    _instrument_httpx,  # pyright: ignore[reportPrivateUsage]
    _instrument_redis,  # pyright: ignore[reportPrivateUsage]
    _instrument_sqlalchemy,  # pyright: ignore[reportPrivateUsage]
    _traces_endpoint,  # pyright: ignore[reportPrivateUsage]
    configure_tracing,
    setup_observability,
)


class _Identity:
    """服务身份替身（提供资源标签值）。"""

    name = "traced-service"
    version = "2.1.0"


class _ResourcesSpy:
    """应用资源注册表替身（记录登记的资源）。"""

    def __init__(self) -> None:
        self.registered: ConcurrentStableList[TracerProviderResource] = ConcurrentStableList()

    def register(self, resource: TracerProviderResource) -> None:
        """登记资源。

        Args:
            resource: 资源对象。
        """
        self.registered.add(resource)


class _FakeCeleryModule:
    """celery 埋点模块替身（真实依赖 `billiard` 缺失时覆盖装配分支）。"""

    class CeleryInstrumentor:
        """埋点器替身。"""

        def instrument(self) -> None:
            """空实现（埋点已生效）。"""
            return None


def _otel_settings() -> Settings:
    """构造 `provider=otel` 的配置。

    Returns:
        Settings: 配置实例。
    """
    settings = Settings()
    settings.tracer.provider = "otel"
    return settings


async def test_configure_tracing_configures_and_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置：建 provider（资源标签 / 幂等）+ 资源释放 flush 并 shutdown。"""
    monkeypatch.setattr(setup, "_configured", False)
    settings = _otel_settings()
    identity = _Identity()

    provider = configure_tracing(settings, identity)

    assert provider is not None
    assert provider.resource.attributes[SERVICE_NAME] == "traced-service"
    assert configure_tracing(settings, identity) is None  # 幂等：进程内只配置一次
    await TracerProviderResource(provider).aclose()


def test_configure_tracing_skips_when_provider_not_otel() -> None:
    """配置：`provider != otel` 时跳过（不建 provider）。"""
    settings = Settings()
    assert configure_tracing(settings, None) is None


def test_build_sampler_maps_known_and_falls_back() -> None:
    """采样器：已知名直取；未知名回退父级比例采样（记告警不阻断）。"""
    settings = Settings()
    settings.tracer.sampler = "always_off"
    assert _build_sampler(settings) is ALWAYS_OFF
    settings.tracer.sampler = "parentbased_traceidratio"
    assert isinstance(_build_sampler(settings), ParentBased)
    # 契约层已收敛为字面量，此处绕过校验直造未知名以覆盖回退分支。
    object.__setattr__(settings.tracer, "sampler", "unknown-sampler")
    assert isinstance(_build_sampler(settings), ParentBased)


def test_traces_endpoint_normalizes_suffix() -> None:
    """端点：基址补全 `/v1/traces`；已是完整端点则原样。"""
    assert _traces_endpoint("http://collector:4318/") == "http://collector:4318/v1/traces"
    assert _traces_endpoint("http://collector:4318/v1/traces") == "http://collector:4318/v1/traces"


def test_instrument_wrapper_swallows_failures() -> None:
    """埋点执行器：成功执行；异常降级（不向上传播）。"""
    called: ConcurrentStableList[str] = ConcurrentStableList()

    def apply() -> None:
        called.add("ok")

    def boom() -> None:
        raise RuntimeError("plugin missing")

    _instrument("ok", apply)
    _instrument("boom", boom)

    assert list(called) == ["ok"]


def test_instrumentation_targets_execute_and_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """各埋点目标：真实执行并还原全局补丁；缺依赖目标经替换导入覆盖。"""
    _instrument_fastapi(FastAPI())

    _instrument_sqlalchemy()
    SQLAlchemyInstrumentor().uninstrument()

    _instrument_redis()
    RedisInstrumentor().uninstrument()

    _instrument_httpx()
    HTTPXClientInstrumentor().uninstrument()

    def _fake_import(name: str) -> Any:
        del name
        return _FakeCeleryModule

    monkeypatch.setattr(setup, "import_module", _fake_import)
    _instrument_celery()


async def test_setup_observability_registers_resource_and_skips_without(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """装配入口：有 resources 即登记释放；无 resources 仅配置不阻断；埋点逐项下发。"""
    labels: ConcurrentStableList[str] = ConcurrentStableList()

    def _record(label: str, apply: Any) -> None:
        del apply
        labels.add(label)

    monkeypatch.setattr(setup, "_instrument", _record)
    monkeypatch.setattr(setup, "_configured", False)
    settings = _otel_settings()

    app = FastAPI()
    resources = _ResourcesSpy()
    app.state.resources = resources
    setup_observability(app, settings)

    assert list(labels) == ["fastapi", "sqlalchemy", "redis", "httpx", "celery"]
    registered = list(resources.registered)
    assert len(registered) == 1
    await registered[0].aclose()

    provider = TracerProvider()

    def _configure(settings: Settings, identity: object | None = None) -> TracerProvider:
        del settings, identity
        return provider

    monkeypatch.setattr(setup, "configure_tracing", _configure)
    setup_observability(FastAPI(), settings)
    provider.shutdown()
