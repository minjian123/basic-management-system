"""字段级变更审计链写入与校验用例（06_02）。"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.audit.helpers import DECEMBER, NOVEMBER, data_event

from bms_core.audit.hashchain import GENESIS_HASH
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shard_repository import LogShardRepository
from bms_core.audit.shards import LOG_TYPE_DATA_AUDIT, month_key
from bms_core.audit.verifier import AuditChainVerifier
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import EventConsumeError
from bms_core.events.base import EventEnvelope
from bms_platform.domains.log.services.writer import AuditLogWriter

pytestmark = pytest.mark.kiwi_id(2515)


async def test_write_chain_and_verify(log_session: AsyncSession) -> None:
    """两条记录按序成链、校验通过；重复 event_id 幂等跳过。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(data_event("d1")) is True
    assert await writer.write(data_event("d2", field="code", old_value="r1", new_value="r2")) is True
    assert await writer.write(data_event("d1")) is False
    await log_session.commit()
    outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_DATA_AUDIT)
    assert outcome.valid is True
    assert outcome.checked_records == 2
    table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(NOVEMBER))
    rows = (await log_session.execute(select(table).order_by(table.c.id))).mappings().all()
    assert rows[0]["prev_hash"] == GENESIS_HASH
    assert rows[1]["prev_hash"] == rows[0]["record_hash"]
    assert rows[0]["domain_key"] == "role"


async def test_cross_month_chain_links_to_previous_month_tail(log_session: AsyncSession) -> None:
    """跨月首条 prev_hash 等于上月同租户末条（月度分片首尾衔接）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(data_event("n1")) is True
    await log_session.commit()
    november_table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(NOVEMBER))
    november_tail = (await log_session.execute(select(november_table.c.record_hash))).scalar_one()

    december_writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: DECEMBER)
    assert await december_writer.write(data_event("x1", occurred_at=DECEMBER)) is True
    await log_session.commit()
    december_table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(DECEMBER))
    december_first = (await log_session.execute(select(december_table.c.prev_hash))).scalar_one()
    assert december_first == november_tail

    outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_DATA_AUDIT)
    assert outcome.valid is True
    assert outcome.checked_records == 2


async def test_tamper_is_located(log_session: AsyncSession) -> None:
    """直接改一条 record_hash 后校验定位到该月 / 该条 / 该记录。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(data_event("t1")) is True
    assert await writer.write(data_event("t2", field="code")) is True
    await log_session.commit()
    table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(NOVEMBER))
    rows = (await log_session.execute(select(table.c.id).order_by(table.c.id))).scalars().all()
    target_id = rows[1]
    await log_session.execute(update(table).where(table.c.id == target_id).values(record_hash="0" * 64))
    await log_session.commit()

    outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_DATA_AUDIT)
    assert outcome.valid is False
    assert outcome.broken_month == month_key(NOVEMBER)
    assert outcome.broken_index == 1
    assert outcome.broken_record_id == target_id


async def test_poison_payload_rejected(log_session: AsyncSession) -> None:
    """缺表名 / 字段名的载荷按毒消息拒绝（不重试、直接死信）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: datetime.now(UTC).replace(tzinfo=None))
    with pytest.raises(EventConsumeError):
        await writer.write(data_event("bad", table=""))
    with pytest.raises(EventConsumeError):
        await writer.write(data_event("bad2", field=""))
    with pytest.raises(EventConsumeError):
        await writer.write(EventEnvelope(event_type="sys.unknown.logged", event_id="bad3"))


async def test_prev_hash_tamper_and_month_subset_verify(log_session: AsyncSession) -> None:
    """改 prev_hash 亦可定位；只校验指定月份时先加载更早月份链尾（跨月衔接仍成立）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: NOVEMBER)
    assert await writer.write(data_event("m1")) is True
    assert await writer.write(data_event("m2", field="code")) is True
    await log_session.commit()
    december_writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: DECEMBER)
    assert await december_writer.write(data_event("m3", occurred_at=DECEMBER)) is True
    await log_session.commit()

    subset = await AuditChainVerifier(log_session, Sha256HashChain()).verify(
        LOG_TYPE_DATA_AUDIT, ConcurrentStableList(["202612"])
    )
    assert subset.valid is True
    assert subset.checked_records == 1

    november_table = LogShardRepository(log_session).table_for(LOG_TYPE_DATA_AUDIT, month_key(NOVEMBER))
    rows = (await log_session.execute(select(november_table.c.id).order_by(november_table.c.id))).scalars().all()
    await log_session.execute(update(november_table).where(november_table.c.id == rows[1]).values(prev_hash="0" * 64))
    await log_session.commit()
    broken = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_DATA_AUDIT)
    assert broken.valid is False
    assert broken.broken_index == 1
