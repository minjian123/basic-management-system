"""审计链校验护栏（06_01）：完整通过 / 篡改定位 / 跨月衔接 / 月份筛选。"""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_platform.domains.log.services.verify import AuditChainVerifier
from bms_platform.domains.log.services.writer import AuditLogWriter
from tests.log.helpers import DECEMBER, NOVEMBER, login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2407)


async def _seed(session: AsyncSession) -> None:
    """两租户、两个月的操作 / 登录日志。"""
    chain = Sha256HashChain()
    november = AuditLogWriter(session, chain, clock=lambda: NOVEMBER)
    december = AuditLogWriter(session, chain, clock=lambda: DECEMBER)
    assert await november.write(operation_event("e1", tenant_id="1001")) is True
    assert await november.write(operation_event("e2", tenant_id="1001")) is True
    assert await november.write(operation_event("e3", tenant_id="2002")) is True
    assert await december.write(operation_event("e4", tenant_id="1001")) is True
    assert await december.write(operation_event("e5", tenant_id="2002")) is True
    assert await november.write(login_event("l1")) is True
    assert await december.write(login_event("l2")) is True
    await session.commit()


async def test_verify_valid_chain(log_session: AsyncSession) -> None:
    """完整链：两类日志均通过，记录数与月份准确。"""
    await _seed(log_session)
    verifier = AuditChainVerifier(log_session, Sha256HashChain())
    operation = await verifier.verify(LOG_TYPE_OPERATION)
    assert operation.valid is True
    assert operation.checked_records == 5
    assert list(operation.checked_months) == ["202611", "202612"]
    login = await verifier.verify(LOG_TYPE_LOGIN)
    assert login.valid is True
    assert login.checked_records == 2


async def test_verify_locates_tampered_record(log_session: AsyncSession) -> None:
    """篡改记录哈希：定位到月份 / 序号 / 记录 ID。"""
    await _seed(log_session)
    repo = LogShardRepository(log_session)
    table = repo.table_for(LOG_TYPE_OPERATION, "202611")
    rows = (await log_session.execute(select(table.c.id).order_by(table.c.id))).scalars().all()
    target = int(rows[1])
    await log_session.execute(update(table).where(table.c.id == target).values(record_hash="0" * 64))
    await log_session.commit()

    outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_OPERATION)
    assert outcome.valid is False
    assert outcome.broken_month == "202611"
    assert outcome.broken_index == 1
    assert outcome.broken_record_id == target
    assert outcome.checked_records == 1


async def test_verify_detects_broken_cross_month_link(log_session: AsyncSession) -> None:
    """篡改次月首条 `prev_hash`：定位到次月首条。"""
    await _seed(log_session)
    table = LogShardRepository.table_for(LOG_TYPE_OPERATION, "202612")
    first = (await log_session.execute(select(table.c.id).order_by(table.c.id).limit(1))).scalar_one()
    await log_session.execute(update(table).where(table.c.id == first).values(prev_hash="f" * 64))
    await log_session.commit()

    outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(LOG_TYPE_OPERATION)
    assert outcome.valid is False
    assert outcome.broken_month == "202612"
    assert outcome.broken_index == 0
    assert outcome.broken_record_id == int(first)


async def test_verify_month_filter_and_empty(log_session: AsyncSession) -> None:
    """指定月份只校验该月；无台账通过且记录数为 0。"""
    verifier = AuditChainVerifier(log_session, Sha256HashChain())
    empty = await verifier.verify(LOG_TYPE_OPERATION)
    assert empty.valid is True
    assert empty.checked_records == 0

    await _seed(log_session)
    first_month = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList(["202611"]))
    assert first_month.valid is True
    assert first_month.checked_records == 3
    filtered = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList(["202612"]))
    assert filtered.valid is True
    assert list(filtered.checked_months) == ["202612"]
    assert filtered.checked_records == 2
    missing = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList(["202001"]))
    assert missing.valid is True
    assert missing.checked_records == 0
