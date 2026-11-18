"""审计链路容量指标护栏（15_01）：指标名常量 / 三处记录函数 / 空指标器放行 / 时延下限。"""

import pytest

from bms_core.audit.observability import (
    GLOBAL_TENANT_LABEL,
    METRIC_AUDIT_LAG,
    METRIC_AUDIT_WRITE,
    METRIC_CHAIN_BROKEN,
    METRIC_CHAIN_VALID,
    METRIC_SHARD_NEXT_MONTH_READY,
    record_audit_write,
    record_chain_verify,
    record_shard_readiness,
)
from bms_core.metrics.prometheus import PrometheusMetrics

pytestmark = pytest.mark.kiwi_id(2531)


def _text(metrics: PrometheusMetrics) -> str:
    """渲染指标文本（断言用）。"""
    rendered = metrics.render()
    assert rendered is not None
    return rendered[0].decode("utf-8")


async def test_metric_names_match_base_registry() -> None:
    """指标名与基座登记同源（避免模块内自造名字）。"""
    from bms_core.metrics.base import METRIC_NAMES

    for name in (
        METRIC_AUDIT_LAG,
        METRIC_AUDIT_WRITE,
        METRIC_CHAIN_VALID,
        METRIC_CHAIN_BROKEN,
        METRIC_SHARD_NEXT_MONTH_READY,
    ):
        assert name in METRIC_NAMES


async def test_record_audit_write_emits_counter_and_lag() -> None:
    """写入计数按日志类型 / 租户，时延直方图观测值与下限截断正确。"""
    metrics = PrometheusMetrics("platform")
    await record_audit_write(metrics, log_type="operation", tenant="1001", lag_seconds=2.5)
    await record_audit_write(metrics, log_type="operation", tenant=GLOBAL_TENANT_LABEL, lag_seconds=-1.0)
    text = _text(metrics)
    assert f'{METRIC_AUDIT_WRITE}{{log_type="operation",service="platform",tenant="1001"}} 1.0' in text
    assert f'{METRIC_AUDIT_WRITE}{{log_type="operation",service="platform",tenant="global"}} 1.0' in text
    assert f'{METRIC_AUDIT_LAG}_count{{log_type="operation",service="platform"}} 2.0' in text
    assert f'{METRIC_AUDIT_LAG}_sum{{log_type="operation",service="platform"}} 2.5' in text


async def test_record_chain_verify_marks_valid_and_counts_broken() -> None:
    """完整记 1 且不计断裂；断裂记 0 并累计一次。"""
    metrics = PrometheusMetrics("platform")
    await record_chain_verify(metrics, log_type="operation", valid=True)
    assert f'{METRIC_CHAIN_VALID}{{log_type="operation",service="platform"}} 1.0' in _text(metrics)
    assert METRIC_CHAIN_BROKEN not in _text(metrics)

    await record_chain_verify(metrics, log_type="operation", valid=False)
    text = _text(metrics)
    assert f'{METRIC_CHAIN_VALID}{{log_type="operation",service="platform"}} 0.0' in text
    assert f'{METRIC_CHAIN_BROKEN}{{log_type="operation",service="platform"}} 1.0' in text


async def test_record_shard_readiness_marks_both_states() -> None:
    """次月分片就绪信号 1 / 0 两态。"""
    assert METRIC_SHARD_NEXT_MONTH_READY == "bms_audit_shard_next_month_ready"
    metrics = PrometheusMetrics("platform")
    await record_shard_readiness(metrics, log_type="login", ready=True)
    assert f'{METRIC_SHARD_NEXT_MONTH_READY}{{log_type="login",service="platform"}} 1.0' in _text(metrics)
    await record_shard_readiness(metrics, log_type="login", ready=False)
    assert f'{METRIC_SHARD_NEXT_MONTH_READY}{{log_type="login",service="platform"}} 0.0' in _text(metrics)


async def test_none_metrics_is_noop() -> None:
    """指标器缺失时空操作（观测面不改变业务结果）。"""
    await record_audit_write(None, log_type="operation", tenant="1001", lag_seconds=1.0)
    await record_chain_verify(None, log_type="operation", valid=False)
    await record_shard_readiness(None, log_type="operation", ready=False)
