"""审计分片基础件护栏（06_02 上移到基座）：结构 / 台账 / 仓储 / 同步门面分支。

Kiwi 2515（与字段级审计用例共用同一编号）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table, create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.audit.hashchain import GENESIS_HASH
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shard_repository import LogShardRepository
from bms_core.audit.shards import (
    LOG_TYPE_DATA_AUDIT,
    LOG_TYPE_LOGIN,
    LOG_TYPE_OPERATION,
    build_shard_table,
    canonical_record,
    month_key,
    month_shift,
    parse_month,
    shard_of_id,
    shard_table_name,
)
from bms_core.audit.verifier import AuditChainVerifier
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.id import id_generator
from bms_core.db.sync import SyncSession
from bms_core.models.base import Base
from bms_core.models.platform.archive import SysArchiveChainTail
from bms_core.models.platform.log import SHARD_STATUS_ARCHIVED, SysAuditShard

pytestmark = [
    pytest.mark.kiwi_id(2515),
    pytest.mark.own_db("内存库自建两张分片表：分片路由与归档链台账本身即被测，不触共享库"),
]

_NOW = datetime(2026, 11, 16, 10, 0, 0)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """进程内 SQLite 会话（仅建分片台账表）。

    Yields:
        AsyncSession: 平台库会话。
    """
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[cast("Table", SysAuditShard.__table__), cast("Table", SysArchiveChainTail.__table__)],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as target:
        yield target
    await engine.dispose()


def _row(
    log_type: str, month: str, *, event_id: str, tenant: int | None = 1001, index: int = 1
) -> ConcurrentStableDict[str, object]:
    """构造一条分片行值（字段按日志类型给全）。"""
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "id": id_generator.next_id() + index,
            "event_id": event_id,
            "tenant_id": tenant,
            "occurred_at": _NOW,
            "prev_hash": "0" * 64,
            "record_hash": "1" * 64,
            "created_at": _NOW,
        }
    )
    if log_type == LOG_TYPE_OPERATION:
        values.set("module", "user")
        values.set("action", "user:create")
        values.set("method", "POST")
        values.set("path", "/api/v1/users")
        values.set("status", 200)
    elif log_type == LOG_TYPE_LOGIN:
        values.set("username", "alice")
        values.set("status", "success")
    else:
        values.set("table_name", "sys_role")
        values.set("record_id", 42)
        values.set("field", "name")
        values.set("domain_key", "role")
    return values


def test_month_helpers_and_parse_guards() -> None:
    """月份键解析与加减；非法形态 / 月份越界即拒；分片表名与规范化字段集合固定。"""
    assert parse_month("202611") == (2026, 11)
    with pytest.raises(ValueError):
        parse_month("20261")
    with pytest.raises(ValueError):
        parse_month("202613")
    assert month_shift("202612", 1) == "202701"
    assert month_shift("202601", -1) == "202512"
    assert month_key(_NOW) == "202611"
    assert shard_table_name(LOG_TYPE_DATA_AUDIT, "202611") == "sys_data_audit_log_202611"
    assert shard_of_id(id_generator.next_id()) == month_key(datetime.now(UTC))
    record = canonical_record(LOG_TYPE_DATA_AUDIT, _row(LOG_TYPE_DATA_AUDIT, "202611", event_id="e1"))
    assert list(record.keys()) == [
        "id",
        "event_id",
        "tenant_id",
        "table_name",
        "record_id",
        "field",
        "old_value",
        "new_value",
        "operator_id",
        "domain_key",
        "occurred_at",
    ]
    assert record["occurred_at"] == "2026-11-16T10:00:00.000000"
    table = build_shard_table(LOG_TYPE_DATA_AUDIT, "sys_data_audit_log_202611")
    assert "domain_key" in table.c


async def test_ensure_shard_ledger_and_conflict(session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """建表 + 台账幂等；并发预创建撞唯一约束按成功处理。"""
    repo = LogShardRepository(session)
    physical = await repo.ensure_shard(LOG_TYPE_DATA_AUDIT, "202611")
    await session.commit()
    assert physical == "sys_data_audit_log_202611"
    assert await repo.months(LOG_TYPE_DATA_AUDIT) == ["202611"]
    assert await repo.ensure_shard(LOG_TYPE_DATA_AUDIT, "202611") == physical

    async def _none(_self: object, _log_type: str, _month: str) -> None:
        return None

    monkeypatch.setattr(LogShardRepository, "_ledger_row", _none)
    assert await repo.ensure_shard(LOG_TYPE_DATA_AUDIT, "202611") == physical


async def test_repository_page_union_and_details(session: AsyncSession) -> None:
    """跨分片分页（UNION + 计数）、按用户 / 用户名筛选、详情与链尾读取。"""
    repo = LogShardRepository(session)
    for month, event_id in (("202610", "p1"), ("202611", "p2")):
        await repo.ensure_shard(LOG_TYPE_OPERATION, month)
        await repo.ensure_shard(LOG_TYPE_LOGIN, month)
        await repo.insert(LOG_TYPE_OPERATION, month, _row(LOG_TYPE_OPERATION, month, event_id=event_id))
        await repo.insert(LOG_TYPE_LOGIN, month, _row(LOG_TYPE_LOGIN, month, event_id=f"l-{event_id}"))
    await session.commit()

    months = await repo.months_between(LOG_TYPE_OPERATION, "202610", "202611")
    rows, total = await repo.page_operation(
        months,
        user_id=None,
        module=None,
        action=None,
        status=None,
        occurred_from=_NOW,
        occurred_to=_NOW,
        offset=0,
        limit=10,
    )
    assert total == 2
    assert len(rows) == 2

    login_rows, login_total = await repo.page_login(
        months,
        username="ali",
        status=None,
        ip=None,
        occurred_from=_NOW,
        occurred_to=_NOW,
        offset=0,
        limit=10,
    )
    assert login_total == 2
    assert login_rows[0]["username"] == "alice"

    empty_fuzzy, _ = await repo.page_login(
        months,
        username="",
        status=None,
        ip=None,
        occurred_from=_NOW,
        occurred_to=_NOW,
        offset=0,
        limit=10,
    )
    assert len(empty_fuzzy) == 2

    first = rows[0]
    detail = await repo.get(LOG_TYPE_OPERATION, "202611", cast("int", first["id"]))
    assert detail is not None
    assert detail["event_id"] in {"p1", "p2"}
    assert await repo.event_exists(LOG_TYPE_OPERATION, "202611", "p2") is True
    assert await repo.last_hash(LOG_TYPE_OPERATION, "202612", 1001) == "1" * 64
    assert await repo.last_hash(LOG_TYPE_OPERATION, "202612", None) == ""


async def test_page_without_months_returns_empty(session: AsyncSession) -> None:
    """台账无分片时查询分页返回空页（不构造 UNION）。"""
    repo = LogShardRepository(session)
    rows, total = await repo.page(
        LOG_TYPE_OPERATION,
        ConcurrentStableList(),
        conditions=ConcurrentStableDict(),
        fuzzy=ConcurrentStableDict[str, str](),
        occurred_from=_NOW,
        occurred_to=_NOW,
        offset=0,
        limit=10,
    )
    assert total == 0
    assert rows == []


async def test_sync_facade_branch() -> None:
    """达梦同步门面路径：`SyncSession` 走同连接建表（分片表 + 台账）。"""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[cast("Table", SysAuditShard.__table__)])
    sync_session = SyncSession(engine)
    try:
        repo = LogShardRepository(sync_session)
        physical = await repo.ensure_shard(LOG_TYPE_LOGIN, "202611")
        await sync_session.commit()
        assert physical == "sys_login_log_202611"
        assert await repo.months(LOG_TYPE_LOGIN) == ["202611"]
        await repo.insert(LOG_TYPE_LOGIN, "202611", _row(LOG_TYPE_LOGIN, "202611", event_id="s1"))
        await sync_session.commit()
        result = await sync_session.execute(select(LogShardRepository.table_for(LOG_TYPE_LOGIN, "202611").c.event_id))
        assert result.scalar_one() == "s1"
    finally:
        await sync_session.aclose()
        engine.dispose()


async def test_archived_month_tail_supports_next_month_verify(session: AsyncSession) -> None:
    """已归档月份（物理表已删）经链尾表参与后续月份校验。"""
    repo = LogShardRepository(session)
    session.add(
        SysAuditShard(
            log_type=LOG_TYPE_OPERATION,
            shard_month="202603",
            physical_table="sys_operation_log_202603",
            status=SHARD_STATUS_ARCHIVED,
        )
    )
    tail_hash = "a" * 64
    session.add(
        SysArchiveChainTail(
            log_type=LOG_TYPE_OPERATION,
            shard_month="202603",
            tenant_key="1001",
            first_prev_hash=GENESIS_HASH,
            last_record_hash=tail_hash,
            record_count=1,
        )
    )
    await session.commit()
    await repo.ensure_shard(LOG_TYPE_OPERATION, "202605")
    occurred = datetime(2026, 5, 2)
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "id": id_generator.next_id(),
            "event_id": "may-1",
            "tenant_id": 1001,
            "module": "m",
            "action": "a",
            "method": "GET",
            "path": "/x",
            "status": 200,
            "occurred_at": occurred,
            "created_at": occurred,
            "prev_hash": tail_hash,
        }
    )
    values["record_hash"] = Sha256HashChain().compute(tail_hash, canonical_record(LOG_TYPE_OPERATION, values))
    await repo.insert(LOG_TYPE_OPERATION, "202605", values)
    await session.commit()

    assert await repo.active_months(LOG_TYPE_OPERATION) == ["202605"]
    assert [row.tenant_key for row in await repo.archived_tails(LOG_TYPE_OPERATION, "202603")] == ["1001"]
    outcome = await AuditChainVerifier(session, Sha256HashChain()).verify(LOG_TYPE_OPERATION, None)
    assert outcome.valid is True
    assert outcome.checked_months == ["202605"]

    tail = (
        await session.execute(select(SysArchiveChainTail).where(SysArchiveChainTail.shard_month == "202603"))
    ).scalar_one()
    tail.last_record_hash = "b" * 64
    await session.commit()
    broken = await AuditChainVerifier(session, Sha256HashChain()).verify(LOG_TYPE_OPERATION, None)
    assert broken.valid is False
    assert broken.broken_month == "202605"


async def test_mark_archived_missing_month_is_noop(session: AsyncSession) -> None:
    """台账无该月分片时标记归档为空操作（幂等容错）。"""
    repo = LogShardRepository(session)
    await repo.mark_archived(LOG_TYPE_OPERATION, "202601")
    assert await repo.ledger(LOG_TYPE_OPERATION) == []


async def test_verifier_scans_earlier_active_month_for_tail(session: AsyncSession) -> None:
    """校验第二个活跃月份时，向前扫描更早的活跃分片取链尾。"""
    repo = LogShardRepository(session)
    chain = Sha256HashChain()
    previous = GENESIS_HASH
    for month, event_id in (("202601", "jan"), ("202602", "feb")):
        await repo.ensure_shard(LOG_TYPE_OPERATION, month)
        occurred = datetime(2026, int(month[4:6]), 2)
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "id": id_generator.next_id(),
                "event_id": event_id,
                "tenant_id": 1001,
                "module": "m",
                "action": "a",
                "method": "GET",
                "path": "/x",
                "status": 200,
                "occurred_at": occurred,
                "created_at": occurred,
                "prev_hash": previous,
            }
        )
        values["record_hash"] = chain.compute(previous, canonical_record(LOG_TYPE_OPERATION, values))
        previous = str(values["record_hash"])
        await repo.insert(LOG_TYPE_OPERATION, month, values)
    await session.commit()
    outcome = await AuditChainVerifier(session, chain).verify(LOG_TYPE_OPERATION, None)
    assert outcome.valid is True
    assert outcome.checked_months == ["202601", "202602"]


async def test_event_exists_many_and_insert_many(session: AsyncSession) -> None:
    """批量判重与批量插入（01_05 批量写入的仓储面）。"""
    repo = LogShardRepository(session)
    month = "202611"
    await repo.ensure_shard(LOG_TYPE_OPERATION, month)
    assert list(await repo.event_exists_many(LOG_TYPE_OPERATION, month, ConcurrentStableList())) == []

    await repo.insert_many(
        LOG_TYPE_OPERATION,
        month,
        ConcurrentStableList(
            [_row(LOG_TYPE_OPERATION, month, event_id="e1"), _row(LOG_TYPE_OPERATION, month, event_id="e2")]
        ),
    )
    await session.commit()
    found = await repo.event_exists_many(LOG_TYPE_OPERATION, month, ConcurrentStableList(["e1", "e3"]))
    assert set(found) == {"e1"}
    await repo.insert_many(LOG_TYPE_OPERATION, month, ConcurrentStableList())
