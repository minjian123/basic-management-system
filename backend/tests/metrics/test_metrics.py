"""指标基座契约测试（Kiwi 44）：继承 / 常量清单 / 依赖清单复用 / 占位空操作 / 依赖解析。"""

from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_metrics
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.fallback.base import DEPENDENCIES as FALLBACK_DEPENDENCIES
from app.main import create_app
from app.metrics.base import DEPENDENCIES, METRIC_KINDS, METRIC_NAMES, BaseMetrics, NullMetrics


@pytest.mark.kiwi_id(44)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseMetrics, BaseCapability)
    assert issubclass(NullMetrics, BaseMetrics)
    assert issubclass(NullMetrics, BaseNullObject)
    assert BaseMetrics.key == "metrics"

    metrics = NullMetrics()
    assert metrics.placeholder is True
    assert "占位实现" in metrics.describe()


@pytest.mark.kiwi_id(44)
def test_metric_kinds_and_names() -> None:
    """指标类型清单（计数器 / 瞬时值 / 直方图）与候选指标名六类无重复。"""
    assert METRIC_KINDS == ("counter", "gauge", "histogram")
    assert METRIC_NAMES == (
        "bms_request_total",
        "bms_request_duration_seconds",
        "bms_dependency_up",
        "bms_ws_connections",
        "bms_mq_backlog",
        "bms_ai_cost",
    )
    assert len(set(METRIC_NAMES)) == len(METRIC_NAMES)
    assert all(name.startswith("bms_") for name in METRIC_NAMES)


@pytest.mark.kiwi_id(44)
def test_dependencies_reuse() -> None:
    """依赖标识清单单向复用降级域（同一对象，标签口径统一）。"""
    assert DEPENDENCIES is FALLBACK_DEPENDENCIES
    assert DEPENDENCIES == (
        "redis",
        "database",
        "rocketmq",
        "elasticsearch",
        "minio",
        "mail_sms",
        "external_api",
    )


@pytest.mark.kiwi_id(44)
async def test_null_metrics_is_noop() -> None:
    """占位指标恒定空操作（不连 Prometheus、不采集）。"""
    metrics = NullMetrics()
    assert await metrics.counter("bms_request_total") is None
    assert await metrics.counter("bms_request_total", value=5.0, labels={"route": "/"}) is None
    assert await metrics.gauge("bms_dependency_up", value=1.0, labels={"dependency": "redis"}) is None
    assert await metrics.histogram("bms_request_duration_seconds", value=0.01) is None


@pytest.mark.kiwi_id(44)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位指标器；路由经 get_metrics 取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.metrics, NullMetrics)

    @app.get("/metrics-probe")
    async def metrics_probe(  # pyright: ignore[reportUnusedFunction]
        metrics: Annotated[BaseMetrics, Depends(get_metrics)],
    ) -> dict[str, object]:
        await metrics.counter("bms_request_total", labels={"route": "/metrics-probe"})
        return {"key": metrics.key, "type": type(metrics).__name__}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics-probe")

    assert resp.status_code == 200
    assert resp.json() == {"key": "metrics", "type": "NullMetrics"}
