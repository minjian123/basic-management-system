"""审计日志链写入护栏（06_01）：幂等 / 链尾衔接 / 跨月 / 两类日志独立 / 毒消息。"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from bms_core.audit.events import LOGIN_LOG_EVENT, OPERATION_LOG_EVENT
from bms_core.audit.hashchain import GENESIS_HASH
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import EventConsumeError
from bms_core.db.sync import SyncSession
from bms_core.events.base import EventEnvelope
from bms_platform.domains.log.repositories.shard import LogShardRepository
from bms_platform.domains.log.schema import LOG_TYPE_LOGIN, LOG_TYPE_OPERATION, canonical_record
from bms_platform.domains.log.services.writer import AuditLogWriter

pytestmark = pytest.mark.kiwi_id(2407)

_NOV = datetime(2026, 11, 15, 10, 0, 0)
_DEC = datetime(2026, 12, 1, 9, 30, 0)


def _operation(
    event_id: str,
    *,
    tenant_id: str | None = "1001",
    status: int | None = 200,
    occurred_at: datetime = _NOV,
    **overrides: object,
) -> EventEnvelope:
    """构造操作日志事件（默认字段齐备；`overrides` 覆盖载荷字段）。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": "7",
            "username": "alice",
            "module": "user",
            "action": "user:create",
            "method": "POST",
            "path": "/api/v1/users",
            "query": '{"a":"1"}',
            "params": '{"password":"***"}',
            "ip": "10.0.0.1",
            "user_agent": "pytest",
            "cost_time": 5,
            "status": status,
        }
    )
    for key, value in overrides.items():
        payload.set(key, value)
    return EventEnvelope(
        event_type=OPERATION_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}" if tenant_id else "global",
    )


def _login(
    event_id: str, *, tenant_id: str = "1001", username: str = "alice", status: str = "success"
) -> EventEnvelope:
    """构造登录日志事件。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": "1",
            "username": username,
            "ip": "10.0.0.1",
            "user_agent": "pytest",
            "status": status,
        }
    )
    if status != "success":
        payload.set("fail_reason", "bad_credentials")
    return EventEnvelope(
        event_type=LOGIN_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=_NOV,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}",
    )


async def _rows(session: AsyncSession, log_type: str, month: str):
    """按分片取全部行（按 id 升序）。"""
    table = LogShardRepository.table_for(log_type, month)
    result = await session.execute(select(table).order_by(table.c.id))
    return result.mappings().all()


async def test_operation_chain_idempotency_and_ledger(log_session: AsyncSession) -> None:
    """首条链头 / 次条衔接 / 重复事件跳过 / 台账幂等。"""
    chain = Sha256HashChain()
    writer = AuditLogWriter(log_session, chain, clock=lambda: _NOV)
    assert await writer.write(_operation("e1")) is True
    assert await writer.write(_operation("e2")) is True
    assert await writer.write(_operation("e1")) is False

    rows = await _rows(log_session, LOG_TYPE_OPERATION, "202611")
    assert len(rows) == 2
    assert rows[0]["prev_hash"] == GENESIS_HASH
    assert rows[1]["prev_hash"] == rows[0]["record_hash"]
    second = ConcurrentStableDict[str, object]({str(key): value for key, value in rows[1].items()})
    expected = chain.compute(rows[0]["record_hash"], canonical_record(LOG_TYPE_OPERATION, second))
    assert rows[1]["record_hash"] == expected

    repo = LogShardRepository(log_session)
    assert list(await repo.months(LOG_TYPE_OPERATION)) == ["202611"]
    await repo.ensure_shard(LOG_TYPE_OPERATION, "202611")
    assert list(await repo.months(LOG_TYPE_OPERATION)) == ["202611"]


async def test_cross_month_links_last_hash_per_tenant(log_session: AsyncSession) -> None:
    """跨月：次月首条 prev = 上月同租户末条；不同租户 / 类型链独立。"""
    chain = Sha256HashChain()
    november = AuditLogWriter(log_session, chain, clock=lambda: _NOV)
    assert await november.write(_operation("e1", tenant_id="1001")) is True
    assert await november.write(_operation("e2", tenant_id="1001")) is True
    assert await november.write(_operation("e3", tenant_id="2002")) is True
    assert await november.write(_login("l1", tenant_id="1001")) is True

    december = AuditLogWriter(log_session, chain, clock=lambda: _DEC)
    assert await december.write(_operation("e4", tenant_id="1001")) is True
    assert await december.write(_operation("e5", tenant_id="2002")) is True
    assert await december.write(_login("l2", tenant_id="1001")) is True
    assert await december.write(_operation("e6", tenant_id="3003")) is True

    nov_rows = await _rows(log_session, LOG_TYPE_OPERATION, "202611")
    dec_rows = await _rows(log_session, LOG_TYPE_OPERATION, "202612")
    nov_last = {int(row["tenant_id"]): row["record_hash"] for row in nov_rows}
    dec_first = {int(row["tenant_id"]): row["prev_hash"] for row in dec_rows}
    assert dec_first[1001] == nov_last[1001]
    assert dec_first[2002] == nov_last[2002]
    assert dec_first[3003] == GENESIS_HASH

    login_dec = await _rows(log_session, LOG_TYPE_LOGIN, "202612")
    login_nov = await _rows(log_session, LOG_TYPE_LOGIN, "202611")
    assert login_dec[0]["prev_hash"] == login_nov[0]["record_hash"]


async def test_unknown_and_malformed_events_raise(log_session: AsyncSession) -> None:
    """未知事件类型 / 缺字段 / 时间非法 / 字段类型非法 → EventConsumeError（毒消息）。"""
    writer = AuditLogWriter(log_session, Sha256HashChain(), clock=lambda: _NOV)
    unknown = EventEnvelope(event_type="sys.other.logged", payload=ConcurrentStableDict[str, object]())
    with pytest.raises(EventConsumeError):
        await writer.write(unknown)

    no_event_id = _operation("x")
    with pytest.raises(EventConsumeError):
        await writer.write(EventEnvelope(event_type=OPERATION_LOG_EVENT, payload=no_event_id.payload))

    with pytest.raises(EventConsumeError):
        await writer.write(_operation("x", module=None))
    with pytest.raises(EventConsumeError):
        await writer.write(_operation("x", tenant_id="not-int"))
    with pytest.raises(EventConsumeError):
        await writer.write(_operation("x", status=None))
    with pytest.raises(EventConsumeError):
        await writer.write(_operation("x", cost_time="bad"))

    login_no_id = _login("l")
    with pytest.raises(EventConsumeError):
        await writer.write(EventEnvelope(event_type=LOGIN_LOG_EVENT, payload=login_no_id.payload))
    with pytest.raises(EventConsumeError):
        await writer.write(
            EventEnvelope(
                event_type=LOGIN_LOG_EVENT,
                payload=ConcurrentStableDict[str, object]({"username": "a", "occurred_at": _NOV.isoformat()}),
                event_id="l2",
            )
        )
    # 缺 occurred_at 时回落信封时间（不属毒消息）——显式断言可正常写入
    fallback = EventEnvelope(
        event_type=LOGIN_LOG_EVENT,
        payload=ConcurrentStableDict[str, object]({"username": "a", "status": "success"}),
        event_id="l3",
        occurred_at=_NOV,
    )
    assert await writer.write(fallback) is True
    # 重复登录事件：幂等跳过
    assert await writer.write(_login("l3")) is False
    # 信封无发生时间：回落当前时刻（`_utc_now`）
    no_time = _operation("no-time")
    no_time.occurred_at = None
    assert await writer.write(no_time) is True


async def test_sync_session_path_writes_shard() -> None:
    """达梦同步方言路径：同步门面建表 + 台账 + 写入（SQLite 同步引擎模拟）。"""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    from bms_core.models.base import Base
    from bms_core.models.platform.log import SysAuditShard

    Base.metadata.create_all(engine, tables=[SysAuditShard.__table__])  # pyright: ignore[reportArgumentType]
    session = SyncSession(engine)
    try:
        repo = LogShardRepository(session)
        assert await repo.ensure_shard(LOG_TYPE_OPERATION, "202611") == "sys_operation_log_202611"
        writer = AuditLogWriter(session, Sha256HashChain(), clock=lambda: _NOV)
        assert await writer.write(_operation("sync-1")) is True
        await session.commit()
        assert list(await repo.months(LOG_TYPE_OPERATION)) == ["202611"]
    finally:
        await session.close()
        engine.dispose()


async def test_ensure_shard_ledger_conflict_rolls_back(
    log_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发预创建：台账唯一冲突回滚但视为成功（表已由另一实例建好）。"""
    repo = LogShardRepository(log_session)
    physical = await repo.ensure_shard(LOG_TYPE_OPERATION, "202611")
    original = repo._ledger_row  # pyright: ignore[reportPrivateUsage]
    calls = 0

    async def _missing_once(log_type: str, month: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        return await original(log_type, month)

    monkeypatch.setattr(repo, "_ledger_row", _missing_once)
    assert await repo.ensure_shard(LOG_TYPE_OPERATION, "202611") == physical
    assert calls >= 1
