"""审计写入与分片容量指标护栏（15_01，Kiwi 2531）：写入计数 / 消费时延 / 次月就绪 / 跨月 0 失败。"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.hashchain import GENESIS_HASH
from bms_core.audit.observability import (
    METRIC_AUDIT_LAG,
    METRIC_AUDIT_WRITE,
    METRIC_SHARD_NEXT_MONTH_READY,
)
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT, LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_core.audit.verifier import AuditChainVerifier
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.services.shard_bootstrap import ensure_audit_shards
from bms_platform.domains.log.services.writer import AuditLogWriter
from tests.log.helpers import NOVEMBER, RecordingMetrics, login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2531)


async def test_writer_records_write_count_and_lag(log_session: AsyncSession) -> None:
    """写入成功：按日志类型 / 租户计数，时延为事件时刻到落库完成。"""
    metrics = RecordingMetrics()
    writer = AuditLogWriter(
        log_session, Sha256HashChain(), clock=lambda: NOVEMBER + timedelta(seconds=2), metrics=metrics
    )
    assert await writer.write(operation_event("m1", tenant_id="1001")) is True

    assert (METRIC_AUDIT_WRITE, 1.0, {"log_type": LOG_TYPE_OPERATION, "tenant": "1001"}) in metrics.counters
    assert (METRIC_AUDIT_LAG, 2.0, {"log_type": LOG_TYPE_OPERATION}) in metrics.histograms


async def test_writer_uses_global_label_without_tenant(log_session: AsyncSession) -> None:
    """无租户事件落 `global` 标签（平台链 / 作业通道口径）。"""
    metrics = RecordingMetrics()
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER, metrics=metrics)
    assert await writer.write(login_event("m2", tenant_id="", occurred_at=NOVEMBER)) is True

    assert (METRIC_AUDIT_WRITE, 1.0, {"log_type": LOG_TYPE_LOGIN, "tenant": "global"}) in metrics.counters


async def test_writer_without_metrics_still_writes(log_session: AsyncSession) -> None:
    """指标器缺失不改变写入结果（观测面不介入业务）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(operation_event("m3")) is True


async def test_ensure_shards_marks_next_month_ready(log_session: AsyncSession) -> None:
    """提前一个月预创建 → 三类日志次月就绪信号均为 1。"""
    metrics = RecordingMetrics()
    months = await ensure_audit_shards(log_session, months_ahead=1, clock=lambda: NOVEMBER, metrics=metrics)
    assert list(months) == ["202611", "202612"]
    ready = [item for item in metrics.gauges if item[0] == METRIC_SHARD_NEXT_MONTH_READY]
    expected = [
        (METRIC_SHARD_NEXT_MONTH_READY, 1.0, {"log_type": log_type})
        for log_type in (LOG_TYPE_OPERATION, LOG_TYPE_LOGIN, LOG_TYPE_DATA_AUDIT)
    ]
    assert ready == expected


async def test_ensure_shards_reports_missing_next_month(log_session: AsyncSession) -> None:
    """只建当月（`months_ahead=0`）→ 次月就绪信号为 0（提前量不足可被规则捕捉）。"""
    metrics = RecordingMetrics()
    months = await ensure_audit_shards(log_session, months_ahead=0, clock=lambda: NOVEMBER, metrics=metrics)
    assert list(months) == ["202611"]
    ready = [item for item in metrics.gauges if item[0] == METRIC_SHARD_NEXT_MONTH_READY]
    assert [(value, labels) for _, value, labels in ready] == [
        (0.0, {"log_type": LOG_TYPE_OPERATION}),
        (0.0, {"log_type": LOG_TYPE_LOGIN}),
        (0.0, {"log_type": LOG_TYPE_DATA_AUDIT}),
    ]


async def test_cross_month_write_succeeds_with_precreated_shard(log_session: AsyncSession) -> None:
    """当月 26 日预创建次月分片后，跨月首条写入直接成功且链头衔接上月尾。"""
    chain = Sha256HashChain()
    november = AuditLogWriter(log_session, chain, clock=lambda: NOVEMBER)
    assert await november.write(operation_event("c1")) is True
    await log_session.commit()
    november_table = LogShardRepository(log_session).table_for(LOG_TYPE_OPERATION, "202611")
    november_tail = (await log_session.execute(select(november_table.c.record_hash))).scalar_one()

    december_26 = datetime(2026, 12, 26, 9, 0, 0)
    await ensure_audit_shards(log_session, months_ahead=1, clock=lambda: december_26)
    await log_session.commit()

    january = AuditLogWriter(log_session, chain, clock=lambda: datetime(2027, 1, 2, 0, 5, 0))
    assert await january.write(operation_event("c2", occurred_at=datetime(2027, 1, 1, 23, 59, 0))) is True
    await log_session.commit()

    january_table = LogShardRepository(log_session).table_for(LOG_TYPE_OPERATION, "202701")
    first_prev = (await log_session.execute(select(january_table.c.prev_hash))).scalar_one()
    assert first_prev == november_tail
    outcome = await AuditChainVerifier(log_session, chain).verify(LOG_TYPE_OPERATION)
    assert outcome.valid is True
    assert GENESIS_HASH not in {first_prev}
