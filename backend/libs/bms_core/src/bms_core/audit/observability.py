"""审计链路容量指标（15_01）：指标名常量与记录函数**单一落点**。

- 指标名与《架构设计 · 可观测性》「指标采集」及基座 `METRIC_NAMES` 同源，模块内不写字面量。
- 三个记录函数在指标器缺失（`None`）时**空操作**：观测面不得改变业务结果，测试与无指标环境不必构造替身。
- 时延口径：`max(0.0, written_at - occurred_at)`——事件发生到审计分片落库完成；缺 `occurred_at` 按 0 计。
- 租户标签取租户主键十进制字符串（与 `sys_outbox.tenant_id` 同源），无租户落 `global`，基数有界。
"""

from __future__ import annotations

from bms_core.metrics.base import BaseMetrics

__all__ = [
    "GLOBAL_TENANT_LABEL",
    "METRIC_AUDIT_LAG",
    "METRIC_AUDIT_WRITE",
    "METRIC_CHAIN_BROKEN",
    "METRIC_CHAIN_VALID",
    "METRIC_SHARD_NEXT_MONTH_READY",
    "record_audit_write",
    "record_chain_verify",
    "record_shard_readiness",
]

METRIC_AUDIT_LAG = "bms_audit_consume_lag_seconds"
"""审计日志消费时延直方图（秒；标签 `log_type`）。"""

METRIC_AUDIT_WRITE = "bms_audit_write_total"
"""审计日志写入计数（标签 `log_type` / `tenant`；`rate()` 即单租户吞吐）。"""

METRIC_CHAIN_VALID = "bms_audit_chain_valid"
"""审计链最近一次校验结果（1 完整 / 0 断裂；标签 `log_type`）。"""

METRIC_CHAIN_BROKEN = "bms_audit_chain_broken_total"
"""审计链累计检出断裂次数（标签 `log_type`）。"""

METRIC_SHARD_NEXT_MONTH_READY = "bms_audit_shard_next_month_ready"
"""次月审计分片是否就绪（1 / 0；标签 `log_type`）。"""

GLOBAL_TENANT_LABEL = "global"
"""无租户事件的租户标签值（平台链 / 作业通道）。"""


async def record_audit_write(
    metrics: BaseMetrics | None,
    *,
    log_type: str,
    tenant: str,
    lag_seconds: float,
) -> None:
    """记录一次审计日志写入（计数 + 消费时延）。

    Args:
        metrics: 指标器（None = 空操作）。
        log_type: 日志类型（`operation` / `login` / `data_audit`）。
        tenant: 租户标签（租户主键字符串；无租户为 `global`）。
        lag_seconds: 事件发生到落库完成的秒数（负数按 0 计）。
    """
    if metrics is None:
        return
    await metrics.counter(METRIC_AUDIT_WRITE, labels={"log_type": log_type, "tenant": tenant})
    await metrics.histogram(METRIC_AUDIT_LAG, value=max(0.0, lag_seconds), labels={"log_type": log_type})


async def record_chain_verify(metrics: BaseMetrics | None, *, log_type: str, valid: bool) -> None:
    """记录一次链校验结果（完整度瞬时值 + 断裂累计计数）。

    Args:
        metrics: 指标器（None = 空操作）。
        log_type: 日志类型。
        valid: 链是否完整。
    """
    if metrics is None:
        return
    await metrics.gauge(METRIC_CHAIN_VALID, value=1.0 if valid else 0.0, labels={"log_type": log_type})
    if not valid:
        await metrics.counter(METRIC_CHAIN_BROKEN, labels={"log_type": log_type})


async def record_shard_readiness(metrics: BaseMetrics | None, *, log_type: str, ready: bool) -> None:
    """记录次月分片就绪信号。

    Args:
        metrics: 指标器（None = 空操作）。
        log_type: 日志类型。
        ready: 次月分片是否已存在（台账已登记）。
    """
    if metrics is None:
        return
    await metrics.gauge(METRIC_SHARD_NEXT_MONTH_READY, value=1.0 if ready else 0.0, labels={"log_type": log_type})
