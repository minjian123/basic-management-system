"""指标采集端点 `/metrics` 测试（Kiwi 2182）：真实实现暴露 / 占位 404 / 请求指标埋点。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.api.metrics import router as metrics_router
from bms_core.api.middleware import RequestLoggingMiddleware
from bms_core.metrics.base import BaseMetrics
from bms_core.metrics.null import NullMetrics
from bms_core.metrics.prometheus import PrometheusMetrics


def _build_app(metrics: BaseMetrics) -> FastAPI:
    """构造最小应用（装配指标器 + 请求日志中间件 + `/metrics` 端点 + 一条业务路由）。"""
    app = FastAPI()
    app.state.metrics = metrics
    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(metrics_router)

    @app.get("/api/v1/users/{user_id}")
    def get_user(user_id: int) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"user_id": user_id}

    return app


@pytest.mark.kiwi_id(2182)
async def test_metrics_endpoint_renders_and_records_request() -> None:
    """真实实现：`/metrics` 200 暴露文本；请求指标 `route` 为路由模板（非原始 path）。"""
    app = _build_app(PrometheusMetrics("platform"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/api/v1/users/42")
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'route="/api/v1/users/{user_id}"' in response.text
    assert 'service="platform"' in response.text


@pytest.mark.kiwi_id(2182)
async def test_metrics_endpoint_404_for_null_provider() -> None:
    """占位实现不暴露指标端点（404），不影响探针与业务。"""
    app = _build_app(NullMetrics())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 404


@pytest.mark.kiwi_id(2182)
async def test_metrics_endpoint_excluded_from_request_metrics() -> None:
    """`/metrics` 自身请求不计入请求指标（排除清单）。"""
    app = _build_app(PrometheusMetrics("platform"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get("/metrics")
        response = await client.get("/metrics")
    assert 'route="/metrics"' not in response.text
