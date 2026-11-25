"""审计链校验护栏（06_01）：完整通过 / 篡改定位 / 跨月衔接 / 月份筛选。

单库叠加口径（《测试规范》§4）：`AuditChainVerifier.verify()` 按**整月分片**遍历、不按租户
过滤，故「整月记录数」「断裂序号」只能在**自己的月份分片**上断言——本文件用 `log_months(ns)`
为每个用例分配一对专属合成月份（前缀含会话盐，跨会话不同），整月口径因此等价于命名空间口径。
篡改用例一律「用完还原」：损坏的行不能留给同会话其它用例的全局校验。
"""

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.namespace import Namespace
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, month_key
from bms_platform.domains.log.services.verify import AuditChainVerifier
from bms_platform.domains.log.services.writer import AuditLogWriter
from tests.log.helpers import log_months, log_tenant, login_event, operation_event

pytestmark = pytest.mark.kiwi_id(2407)


async def _seed(session: AsyncSession, ns: Namespace) -> tuple[str, str]:
    """两租户、两个月的操作 / 登录日志（月份与租户均取自本用例命名空间）。

    Args:
        session: 共享平台库写会话。
        ns: 用例命名空间。

    Returns:
        tuple[str, str]: （较早月份键, 次月份键）。
    """
    first, second = log_months(ns)
    tenant_a, tenant_b = log_tenant(ns, 0), log_tenant(ns, 1)
    chain = Sha256HashChain()
    earlier = AuditLogWriter(session, chain, clock=lambda: first)
    later = AuditLogWriter(session, chain, clock=lambda: second)
    assert await earlier.write(operation_event(ns.code("e1"), tenant_id=str(tenant_a))) is True
    assert await earlier.write(operation_event(ns.code("e2"), tenant_id=str(tenant_a))) is True
    assert await earlier.write(operation_event(ns.code("e3"), tenant_id=str(tenant_b))) is True
    assert await later.write(operation_event(ns.code("e4"), tenant_id=str(tenant_a))) is True
    assert await later.write(operation_event(ns.code("e5"), tenant_id=str(tenant_b))) is True
    assert await earlier.write(login_event(ns.code("l1"), tenant_id=str(tenant_a))) is True
    assert await later.write(login_event(ns.code("l2"), tenant_id=str(tenant_a))) is True
    await session.commit()
    return month_key(first), month_key(second)


async def test_verify_valid_chain(log_session: AsyncSession, ns: Namespace) -> None:
    """完整链：两类日志均通过，记录数与月份准确。"""
    first_month, second_month = await _seed(log_session, ns)
    months = ConcurrentStableList([first_month, second_month])
    verifier = AuditChainVerifier(log_session, Sha256HashChain())
    operation = await verifier.verify(LOG_TYPE_OPERATION, months)
    assert operation.valid is True
    assert operation.checked_records == 5
    assert list(operation.checked_months) == [first_month, second_month]
    login = await verifier.verify(LOG_TYPE_LOGIN, months)
    assert login.valid is True
    assert login.checked_records == 2


async def test_verify_locates_tampered_record(log_session: AsyncSession, ns: Namespace) -> None:
    """篡改记录哈希：定位到月份 / 序号 / 记录 ID（用完还原，不污染他人全局校验）。"""
    first_month, _ = await _seed(log_session, ns)
    repo = LogShardRepository(log_session)
    table = repo.table_for(LOG_TYPE_OPERATION, first_month)
    rows = (await log_session.execute(select(table).order_by(table.c.id))).mappings().all()
    target = int(str(rows[1]["id"]))
    original = str(rows[1]["record_hash"])
    # 不提交篡改：校验读同一会话即可见，避免其他 worker 的全局校验读到损坏的行
    await log_session.execute(update(table).where(table.c.id == target).values(record_hash="0" * 64))
    try:
        outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(
            LOG_TYPE_OPERATION, ConcurrentStableList([first_month])
        )
        assert outcome.valid is False
        assert outcome.broken_month == first_month
        assert outcome.broken_index == 1
        assert outcome.broken_record_id == target
        assert outcome.checked_records == 1
    finally:
        await log_session.execute(update(table).where(table.c.id == target).values(record_hash=original))
        await log_session.commit()


async def test_verify_detects_broken_cross_month_link(log_session: AsyncSession, ns: Namespace) -> None:
    """篡改次月首条 `prev_hash`：定位到次月首条（用完还原）。"""
    first_month, second_month = await _seed(log_session, ns)
    table = LogShardRepository.table_for(LOG_TYPE_OPERATION, second_month)
    row = (await log_session.execute(select(table).order_by(table.c.id).limit(1))).mappings().one()
    first = int(str(row["id"]))
    original = str(row["prev_hash"])
    await log_session.execute(update(table).where(table.c.id == first).values(prev_hash="f" * 64))
    try:
        outcome = await AuditChainVerifier(log_session, Sha256HashChain()).verify(
            LOG_TYPE_OPERATION, ConcurrentStableList([first_month, second_month])
        )
        assert outcome.valid is False
        assert outcome.broken_month == second_month
        assert outcome.broken_index == 0
        assert outcome.broken_record_id == first
    finally:
        await log_session.execute(update(table).where(table.c.id == first).values(prev_hash=original))
        await log_session.commit()


async def test_verify_month_filter_and_empty(log_session: AsyncSession, ns: Namespace) -> None:
    """指定月份只校验该月；本用例月份尚无分片时通过且记录数为 0。"""
    first, second = log_months(ns)
    first_month, second_month = month_key(first), month_key(second)
    verifier = AuditChainVerifier(log_session, Sha256HashChain())
    empty = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList([first_month, second_month]))
    assert empty.valid is True
    assert empty.checked_records == 0

    await _seed(log_session, ns)
    first_only = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList([first_month]))
    assert first_only.valid is True
    assert first_only.checked_records == 3
    filtered = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList([second_month]))
    assert filtered.valid is True
    assert list(filtered.checked_months) == [second_month]
    assert filtered.checked_records == 2
    missing = await verifier.verify(LOG_TYPE_OPERATION, ConcurrentStableList(["202001"]))
    assert missing.valid is True
    assert missing.checked_records == 0
