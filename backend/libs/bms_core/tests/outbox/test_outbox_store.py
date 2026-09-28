"""事务性发件箱存储用例（Kiwi 2172 / 2174）：同库同事务写入 / 取待投递顺序 / 标记 / 退避死信 / 重放 / 看板
/ 事件契约版本与签发校验模式（2174）。

测试库：临时 SQLite（建发件箱三表）。每次数据库交互均显式事务（会话自动开事务，勿混用）。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.exceptions import ConfigError, EventContractError
from bms_core.events.base import DEFAULT_EVENT_VERSION, EventEnvelope
from bms_core.events.contracts import (
    EVENT_CONTRACT_MODE_ENFORCE,
    EVENT_CONTRACT_MODE_WARN,
    EventContract,
)
from bms_core.models.outbox import SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import (
    DEAD_LETTER_STATUS_IGNORED,
    DEAD_LETTER_STATUS_PENDING,
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_DELIVERED,
    OUTBOX_STATUS_PENDING,
)
from bms_core.outbox.store import SqlOutboxStore


def _now() -> datetime:
    """当前 UTC 时间（naive）。"""
    return datetime.now(UTC).replace(tzinfo=None)


async def _count(session: AsyncSession, model: Any) -> int:
    """计数（显式事务）。"""
    async with session.begin():
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _event_id_by_payload(session: AsyncSession, value: int) -> str:
    """按 payload.n 取事件 ID（测试辅助，显式事务）。"""
    async with session.begin():
        rows = (await session.execute(select(SysOutbox))).scalars().all()
    for row in rows:
        if row.payload.get("n") == value:
            return row.event_id
    raise AssertionError(f"未找到 payload.n={value} 的事件")


@pytest.mark.kiwi_id(2172)
async def test_enqueue_defaults_and_rollback(session: AsyncSession) -> None:
    """写入缺省补齐 event_id / occurred_at；事务回滚不发事件。"""
    store = SqlOutboxStore()
    async with session.begin():
        event_id = await store.enqueue(session, EventEnvelope(event_type="order.created", payload={"id": 1}))
    assert event_id

    async with session.begin():
        row = (await session.execute(select(SysOutbox))).scalars().one()
        assert row.event_id == event_id
        assert row.occurred_at is not None
        assert row.status == OUTBOX_STATUS_PENDING
        assert row.retry_count == 0

    with pytest.raises(RuntimeError):
        async with session.begin():
            await store.enqueue(session, EventEnvelope(event_type="order.created"))
            raise RuntimeError("业务失败回滚")
    assert await _count(session, SysOutbox) == 1


@pytest.mark.kiwi_id(2172)
async def test_claim_pending_order_and_retry_gate(session: AsyncSession) -> None:
    """取待投递：同聚合仅队首、未到期队首阻塞同聚合、不同聚合独立。"""
    store = SqlOutboxStore()
    async with session.begin():
        first = await store.enqueue(session, EventEnvelope(event_type="e.a", aggregate_key="A", payload={"n": 1}))
        second = await store.enqueue(session, EventEnvelope(event_type="e.a", aggregate_key="A", payload={"n": 2}))
        third = await store.enqueue(session, EventEnvelope(event_type="e.b", aggregate_key="B", payload={"n": 3}))
    assert third == await _event_id_by_payload(session, 3)

    async with session.begin():
        claimed = await store.claim_pending(session, now=_now(), limit=10)
    assert [record.event_id for record in claimed] == [first, third]
    assert second not in [record.event_id for record in claimed]

    # 队首未到期 → 同聚合后续仍阻塞
    async with session.begin():
        await store.mark_failed(session, first, "boom", max_retries=5, backoff=3600)
    async with session.begin():
        claimed = await store.claim_pending(session, now=_now(), limit=10)
    assert first not in [record.event_id for record in claimed]
    assert second not in [record.event_id for record in claimed]


@pytest.mark.kiwi_id(2172)
async def test_mark_delivered_and_failed_dead_letter(session: AsyncSession) -> None:
    """标记已投递；失败指数退避、超上限转死信并插死信行。"""
    store = SqlOutboxStore()
    async with session.begin():
        delivered = await store.enqueue(session, EventEnvelope(event_type="e.deliver"))
        failing = await store.enqueue(session, EventEnvelope(event_type="e.fail", tenant_id="t1"))
    async with session.begin():
        await store.mark_delivered(session, delivered)
    async with session.begin():
        row = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == delivered))).scalars().one()
        assert row.status == OUTBOX_STATUS_DELIVERED
        assert row.delivered_at is not None

    async with session.begin():
        dead = await store.mark_failed(session, failing, "x" * 600, max_retries=2, backoff=10)
    assert dead is False
    async with session.begin():
        row = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == failing))).scalars().one()
        assert row.retry_count == 1
        assert row.next_retry_at is not None
        assert len(row.error_msg or "") == 512

    async with session.begin():
        dead = await store.mark_failed(session, failing, "again", max_retries=2, backoff=10)
    assert dead is True
    async with session.begin():
        row = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == failing))).scalars().one()
        assert row.status == OUTBOX_STATUS_DEAD
        letter = (await session.execute(select(SysEventDeadLetter))).scalars().one()
    assert letter.event_id == failing
    assert letter.source == "outbox"
    assert letter.tenant_id == "t1"
    assert letter.status == DEAD_LETTER_STATUS_PENDING

    # 不存在的事件 ID：标记为无操作 / 未命中
    async with session.begin():
        assert await store.mark_failed(session, "ghost", "x", max_retries=2, backoff=1) is False
        await store.mark_delivered(session, "ghost")


@pytest.mark.kiwi_id(2172)
async def test_replay_and_backlog(session: AsyncSession) -> None:
    """重放按 事件 ID / 类型 / 时间 重置为待投递；积压计数。"""
    store = SqlOutboxStore()
    async with session.begin():
        a = await store.enqueue(session, EventEnvelope(event_type="e.a"))
        b = await store.enqueue(session, EventEnvelope(event_type="e.b"))
    async with session.begin():
        await store.mark_delivered(session, a)
        await store.mark_failed(session, b, "boom", max_retries=1, backoff=1)
    async with session.begin():
        assert await store.backlog(session) == 0

    async with session.begin():
        assert await store.replay(session, event_id=a) == 1
    async with session.begin():
        assert await store.backlog(session) == 1

    async with session.begin():
        assert await store.replay(session, event_type="e.b") == 1
    async with session.begin():
        assert await store.backlog(session) == 2

    # 时间下限筛选（未来时间 → 0 条）
    async with session.begin():
        await store.mark_delivered(session, a)
        await store.mark_delivered(session, b)
        assert await store.replay(session, since=_now() + timedelta(days=1)) == 0


@pytest.mark.kiwi_id(2172)
async def test_dead_letter_board(session: AsyncSession) -> None:
    """死信看板：列表 / 筛选 / 详情 / 状态读写。"""
    store = SqlOutboxStore()
    async with session.begin():
        event_id = await store.enqueue(session, EventEnvelope(event_type="e.dead"))
    async with session.begin():
        await store.mark_failed(session, event_id, "boom", max_retries=1, backoff=1)

    async with session.begin():
        rows, total = await store.list_dead_letters(session, status=DEAD_LETTER_STATUS_PENDING, source="outbox")
    assert total == 1 and len(rows) == 1
    dead_id = rows[0].id
    async with session.begin():
        assert (await store.get_dead_letter(session, dead_id)) is not None
        assert await store.get_dead_letter(session, 999999) is None

    async with session.begin():
        assert await store.set_dead_letter_status(session, dead_id, DEAD_LETTER_STATUS_IGNORED) is True
        assert await store.set_dead_letter_status(session, 999999, DEAD_LETTER_STATUS_IGNORED) is False
    async with session.begin():
        rows, total = await store.list_dead_letters(session, status=DEAD_LETTER_STATUS_IGNORED)
        assert total == 1 and rows[0].status == DEAD_LETTER_STATUS_IGNORED
        assert (await store.list_dead_letters(session, source="consumer"))[1] == 0
        assert (await store.list_dead_letters(session, offset=10, limit=5))[1] == 1


@pytest.mark.kiwi_id(2172)
async def test_claim_limit_and_replay_edges(session: AsyncSession) -> None:
    """取待投递 limit 边界与截断；重放 limit 与无匹配返回 0。"""
    store = SqlOutboxStore()
    async with session.begin():
        await store.enqueue(session, EventEnvelope(event_type="e1", aggregate_key="A"))
        await store.enqueue(session, EventEnvelope(event_type="e2", aggregate_key="B"))
        await store.enqueue(session, EventEnvelope(event_type="e3", aggregate_key="C"))

    async with session.begin():
        assert await store.claim_pending(session, now=_now(), limit=0) == []
        claimed = await store.claim_pending(session, now=_now(), limit=2)
    assert len(claimed) == 2

    async with session.begin():
        for record in claimed:
            await store.mark_delivered(session, record.event_id)
    async with session.begin():
        assert await store.replay(session, event_id="ghost") == 0
        assert await store.replay(session, aggregate_key="A") == 1
        assert await store.replay(session, limit=1) == 1


@pytest.mark.kiwi_id(2174)
async def test_event_version_defaults_and_persistence(session: AsyncSession) -> None:
    """版本缺省补齐（未登记回落 1.0.0）、显式版本落库与投递重建保真。"""
    store = SqlOutboxStore()
    async with session.begin():
        first = await store.enqueue(session, EventEnvelope(event_type="e.a", payload={"n": 1}))
        second = await store.enqueue(session, EventEnvelope(event_type="e.a", event_version="2.3.4", payload={"n": 2}))
    async with session.begin():
        versions = {
            row.event_id: row.event_version for row in (await session.execute(select(SysOutbox))).scalars().all()
        }
    assert versions[first] == DEFAULT_EVENT_VERSION
    assert versions[second] == "2.3.4"

    async with session.begin():
        claimed = await store.claim_pending(session, now=_now(), limit=10)
    by_id = {record.event_id: record for record in claimed}
    assert by_id[second].to_envelope().event_version == "2.3.4"


@pytest.mark.kiwi_id(2174)
async def test_contract_mode_enforce_and_warn(session: AsyncSession) -> None:
    """签发契约校验三态：enforce 拒发未登记 / 非法版本且事务回滚；warn 放行；登记契约补齐契约版本。"""
    contract = EventContract(event_type="e.a", version="1.2.0", fields={})

    def _resolver(event_type: str) -> EventContract | None:
        return contract if event_type == "e.a" else None

    enforce = SqlOutboxStore(contract_mode=EVENT_CONTRACT_MODE_ENFORCE, contract_resolver=_resolver)
    async with session.begin():
        event_id = await enforce.enqueue(session, EventEnvelope(event_type="e.a"))
    async with session.begin():
        row = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == event_id))).scalars().one()
    assert row.event_version == "1.2.0"

    with pytest.raises(EventContractError):
        async with session.begin():
            await enforce.enqueue(session, EventEnvelope(event_type="e.unknown"))
    with pytest.raises(EventContractError):
        async with session.begin():
            await enforce.enqueue(session, EventEnvelope(event_type="e.a", event_version="bad"))
    assert await _count(session, SysOutbox) == 1

    warn = SqlOutboxStore(contract_mode=EVENT_CONTRACT_MODE_WARN, contract_resolver=_resolver)
    async with session.begin():
        await warn.enqueue(session, EventEnvelope(event_type="e.unknown"))
        await warn.enqueue(session, EventEnvelope(event_type="e.a", event_version="bad"))
    assert await _count(session, SysOutbox) == 3


@pytest.mark.kiwi_id(2174)
def test_contract_mode_invalid_rejected() -> None:
    """签发契约校验模式非法即拒（配置错误）。"""
    with pytest.raises(ConfigError):
        SqlOutboxStore(contract_mode="loud")
