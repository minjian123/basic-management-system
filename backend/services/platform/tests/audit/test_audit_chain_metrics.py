"""审计链校验容量指标护栏（15_01，Kiwi 2531）：完整 / 断裂 / 字段级变更 / 分片就绪。"""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.audit.helpers import NOVEMBER, data_event
from tests.log.helpers import RecordingMetrics, operation_event

from bms_core.audit.observability import METRIC_CHAIN_BROKEN, METRIC_CHAIN_VALID, METRIC_SHARD_NEXT_MONTH_READY
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT, LOG_TYPE_OPERATION
from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.domains.audit.api.chain import verify_data_audit_chain
from bms_platform.domains.log.api.internal_audit import ensure_shards, verify_chain
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schemas.log import EnsureShardsRequest, VerifyRequest
from bms_platform.domains.log.services.writer import AuditLogWriter

pytestmark = pytest.mark.kiwi_id(2531)


def _gauges(metrics: RecordingMetrics, name: str) -> ConcurrentStableList[tuple[float, object]]:
    """取某指标的全部（值, 标签）。"""
    return ConcurrentStableList((value, labels) for metric, value, labels in metrics.gauges if metric == name)


async def test_internal_verify_marks_chain_valid(log_session: AsyncSession) -> None:
    """内部端点校验完整链：完整度 1、不计断裂。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(operation_event("v1")) is True
    await log_session.commit()

    metrics = RecordingMetrics()
    result = await verify_chain(log_session, Sha256HashChain(), metrics, VerifyRequest(log_type=LOG_TYPE_OPERATION))
    assert result.data is not None
    assert result.data.valid is True
    assert list(_gauges(metrics, METRIC_CHAIN_VALID)) == [(1.0, {"log_type": LOG_TYPE_OPERATION})]
    assert [item for item in metrics.counters if item[0] == METRIC_CHAIN_BROKEN] == []


async def test_internal_verify_marks_broken_and_counts(log_session: AsyncSession) -> None:
    """内部端点校验被篡改链：完整度 0、断裂计数 +1。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(operation_event("v2")) is True
    assert await writer.write(operation_event("v3")) is True
    await log_session.commit()
    table = LogShardRepository.table_for(LOG_TYPE_OPERATION, "202611")
    first = (await log_session.execute(select(table.c.id).order_by(table.c.id).limit(1))).scalar_one()
    await log_session.execute(update(table).where(table.c.id == first).values(record_hash="0" * 64))
    await log_session.commit()

    metrics = RecordingMetrics()
    result = await verify_chain(log_session, Sha256HashChain(), metrics, VerifyRequest(log_type=LOG_TYPE_OPERATION))
    assert result.data is not None
    assert result.data.valid is False
    assert list(_gauges(metrics, METRIC_CHAIN_VALID)) == [(0.0, {"log_type": LOG_TYPE_OPERATION})]
    assert (METRIC_CHAIN_BROKEN, 1.0, {"log_type": LOG_TYPE_OPERATION}) in metrics.counters


async def test_data_audit_verify_marks_chain_valid(log_session: AsyncSession) -> None:
    """用户面字段级变更链校验同样记录指标。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(data_event("d1")) is True
    await log_session.commit()

    metrics = RecordingMetrics()
    result = await verify_data_audit_chain(log_session, Sha256HashChain(), metrics, None)
    assert result.data is not None
    assert result.data.valid is True
    assert list(_gauges(metrics, METRIC_CHAIN_VALID)) == [(1.0, {"log_type": LOG_TYPE_DATA_AUDIT})]


async def test_ensure_shards_endpoint_records_readiness(log_session: AsyncSession) -> None:
    """预创建端点记录三类日志的次月就绪信号。"""
    metrics = RecordingMetrics()
    result = await ensure_shards(log_session, metrics, EnsureShardsRequest(months_ahead=1))
    assert result.data is not None
    assert len(result.data.months) == 2
    ready = _gauges(metrics, METRIC_SHARD_NEXT_MONTH_READY)
    assert [value for value, _ in ready] == [1.0, 1.0, 1.0]
