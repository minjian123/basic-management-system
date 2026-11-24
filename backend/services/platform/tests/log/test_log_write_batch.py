"""审计日志批量写入护栏（01_05）：链连续 / 幂等 / 毒消息隔离 / 月度衔接。

依据《详细设计 · 01_05 审计链消费性能优化》§4.4：批内每链只查一次链尾、在内存逐条衔接，
一批一次写入；命中幂等跳过，毒消息不连坐整批。
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.hashchain import GENESIS_HASH
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.events.base import EventEnvelope
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION
from bms_platform.domains.log.services.writer import AuditLogWriter

pytestmark = pytest.mark.kiwi_id(2407)

_NOV = datetime(2026, 11, 15, 10, 0, 0)
_DEC = datetime(2026, 12, 1, 9, 30, 0)


def _tid() -> str:
    """本用例专属租户（分片表上的链按租户隔离，不与他人串链）。"""
    return str(900_000_000 + uuid4().int % 99_999_999)


def _operation(event_id: str, *, tenant_id: str = "1001") -> EventEnvelope:
    """构造操作日志事件。

    Args:
        event_id: 事件 ID。
        tenant_id: 租户主键（字符串）。

    Returns:
        EventEnvelope: 事件信封。
    """
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": "7",
            "username": "alice",
            "module": "user",
            "action": "user:create",
            "method": "POST",
            "path": "/api/v1/users",
            "status": 200,
        }
    )
    return EventEnvelope(
        event_type="sys.operation.logged",
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=_NOV,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}",
    )


def _login(event_id: str, *, tenant_id: str = "1001") -> EventEnvelope:
    """构造登录日志事件。

    Args:
        event_id: 事件 ID。
        tenant_id: 租户主键（字符串）。

    Returns:
        EventEnvelope: 事件信封。
    """
    payload = ConcurrentStableDict[str, object](
        {"tenant_id": tenant_id, "user_id": "1", "username": "alice", "status": "success"}
    )
    return EventEnvelope(
        event_type="sys.login.logged",
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=_NOV,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}",
    )


async def _rows(session: AsyncSession, log_type: str, month: str, *, tenant_id: str | None = None):
    """按分片取行（按 id 升序；给了 `tenant_id` 只取该租户的链）。"""
    table = LogShardRepository.table_for(log_type, month)
    statement = select(table).order_by(table.c.id)
    if tenant_id is not None:
        statement = statement.where(table.c.tenant_id == tenant_id)
    result = await session.execute(statement)
    return result.mappings().all()


async def test_batch_write_is_chain_continuous(log_session: AsyncSession) -> None:
    """批内同链逐条衔接；跨链独立；一批写入条数与结果一致。"""
    tid = _tid()
    tag = uuid4().hex[:8]
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: _NOV)
    events = ConcurrentStableList(
        [
            _operation(f"{tag}-e1", tenant_id=tid),
            _operation(f"{tag}-e2", tenant_id=tid),
            _login(f"{tag}-l1", tenant_id=tid),
            _operation(f"{tag}-e3", tenant_id=tid),
        ]
    )
    outcomes = await writer.write_batch(events)

    assert [item.kind for item in outcomes] == ["succeeded"] * 4
    op_rows = await _rows(log_session, LOG_TYPE_OPERATION, "202611", tenant_id=tid)
    assert len(op_rows) == 3
    assert op_rows[0]["prev_hash"] == GENESIS_HASH
    assert op_rows[1]["prev_hash"] == op_rows[0]["record_hash"]
    assert op_rows[2]["prev_hash"] == op_rows[1]["record_hash"]
    login_rows = await _rows(log_session, LOG_TYPE_LOGIN, "202611", tenant_id=tid)
    assert len(login_rows) == 1
    assert login_rows[0]["prev_hash"] == GENESIS_HASH


async def test_batch_skips_existing_and_duplicate_ids(log_session: AsyncSession) -> None:
    """库内已存在与批内重复的事件都返回 skipped，只写一条。"""
    tid = _tid()
    tag = uuid4().hex[:8]
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: _NOV)
    assert await writer.write(_operation(f"{tag}-e1", tenant_id=tid)) is True

    outcomes = await writer.write_batch(
        ConcurrentStableList(
            [
                _operation(f"{tag}-e1", tenant_id=tid),
                _operation(f"{tag}-e2", tenant_id=tid),
                _operation(f"{tag}-e2", tenant_id=tid),
            ]
        )
    )
    assert [item.kind for item in outcomes] == ["skipped", "succeeded", "skipped"]
    assert len(await _rows(log_session, LOG_TYPE_OPERATION, "202611", tenant_id=tid)) == 2


async def test_batch_isolates_malformed_and_unknown(log_session: AsyncSession) -> None:
    """未知类型 / 缺必填字段返回不可重试失败；同批正常事件照常写入。"""
    tid = _tid()
    tag = uuid4().hex[:8]
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: _NOV)
    unknown = EventEnvelope(
        event_type="sys.other.logged", payload=ConcurrentStableDict[str, object](), event_id=f"{tag}-x1"
    )
    malformed = EventEnvelope(
        event_type="sys.operation.logged",
        payload=ConcurrentStableDict[str, object]({"tenant_id": tid}),
        event_id=f"{tag}-x2",
    )
    outcomes = await writer.write_batch(
        ConcurrentStableList([unknown, malformed, _operation(f"{tag}-e1", tenant_id=tid)])
    )

    assert outcomes[0].kind == "failed"
    assert outcomes[0].retryable is False
    assert outcomes[1].kind == "failed"
    assert outcomes[1].retryable is False
    assert outcomes[2].kind == "succeeded"
    assert len(await _rows(log_session, LOG_TYPE_OPERATION, "202611", tenant_id=tid)) == 1


async def test_batch_empty_is_noop(log_session: AsyncSession) -> None:
    """空批次不建表、不写入。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: _NOV)
    assert list(await writer.write_batch(ConcurrentStableList())) == []


async def test_batch_cross_month_links_previous_shard(log_session: AsyncSession) -> None:
    """跨批跨月：次月批次首条 prev 取上月同租户末条。"""
    tid = _tid()
    tag = uuid4().hex[:8]
    chain = Sha256HashChain()
    november = AuditLogWriter(log_session, chain, clock=lambda: _NOV)
    assert await november.write(_operation(f"{tag}-e1", tenant_id=tid)) is True

    december = AuditLogWriter(log_session, chain, clock=lambda: _DEC)
    outcomes = await december.write_batch(
        ConcurrentStableList([_operation(f"{tag}-e2", tenant_id=tid), _operation(f"{tag}-e3", tenant_id=tid)])
    )
    assert [item.kind for item in outcomes] == ["succeeded", "succeeded"]

    nov_rows = await _rows(log_session, LOG_TYPE_OPERATION, "202611", tenant_id=tid)
    dec_rows = await _rows(log_session, LOG_TYPE_OPERATION, "202612", tenant_id=tid)
    assert dec_rows[0]["prev_hash"] == nov_rows[-1]["record_hash"]
    assert dec_rows[1]["prev_hash"] == dec_rows[0]["record_hash"]
