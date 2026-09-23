"""Prometheus 指标真实实现测试（Kiwi 2182）：契约 / 记录与渲染 / 标签注入 / 冲突早失败。"""

import pytest

from bms_core.core.capability import BaseNullObject
from bms_core.metrics.base import BaseMetrics
from bms_core.metrics.null import NullMetrics
from bms_core.metrics.prometheus import SERVICE_LABEL, PrometheusMetrics


def _render(metrics: PrometheusMetrics) -> str:
    """渲染指标文本（断言用）。

    Args:
        metrics: Prometheus 指标实现。

    Returns:
        str: Prometheus 文本格式。
    """
    rendered = metrics.render()
    assert rendered is not None
    return rendered[0].decode("utf-8")


@pytest.mark.kiwi_id(2182)
def test_contract_and_provider() -> None:
    """真实实现继承指标契约、provider 为 prometheus、非占位。"""
    assert issubclass(PrometheusMetrics, BaseMetrics)
    assert not issubclass(PrometheusMetrics, BaseNullObject)
    assert PrometheusMetrics.plugin_name == "prometheus"
    assert PrometheusMetrics.key == "metrics"


@pytest.mark.kiwi_id(2182)
async def test_records_and_renders_with_service_label() -> None:
    """三入口记录后渲染文本含指标名与注入的 `service` 标签。"""
    metrics = PrometheusMetrics("platform")
    await metrics.counter("bms_request_total", labels={"method": "GET", "route": "/x/{id}", "status": "200"})
    await metrics.gauge("bms_dependency_up", value=1.0, labels={"dependency": "redis"})
    await metrics.histogram("bms_request_duration_seconds", value=0.12, labels={"method": "GET", "route": "/x/{id}"})

    text = _render(metrics)
    assert "# TYPE bms_request_total counter" in text
    assert "bms_dependency_up" in text
    assert "bms_request_duration_seconds_bucket" in text
    assert f'{SERVICE_LABEL}="platform"' in text
    assert 'route="/x/{id}"' in text


@pytest.mark.kiwi_id(2182)
async def test_service_label_injected_overrides_conflict() -> None:
    """`service` 标签由实现统一注入（调用方无需传，重复传同值等价）。"""
    metrics = PrometheusMetrics("platform")
    await metrics.counter("bms_request_total", labels={"service": "platform", "status": "200"})
    text = _render(metrics)
    assert text.count('service="platform"') >= 1


@pytest.mark.kiwi_id(2182)
async def test_same_name_conflicting_kind_fails_fast() -> None:
    """同名指标跨类型登记早失败（防静默串指标）。"""
    metrics = PrometheusMetrics("platform")
    await metrics.counter("bms_request_total")
    with pytest.raises(ValueError, match="定义冲突"):
        await metrics.gauge("bms_request_total", value=1.0)


@pytest.mark.kiwi_id(2182)
def test_null_metrics_render_none() -> None:
    """占位实现不提供渲染能力（`render()` 返回 None，端点按不支持处理）。"""
    assert NullMetrics().render() is None
