"""07B `06_01` 步 3 用例（Kiwi 2442）：未确认事件在 provider 切换中的处置。

**这一态的风险是「丢」与「双写」**：事件已写进发件箱但还没被下游确认，此时换 provider——
若把未确认的行当已投递就丢了，若两个 provider 同时跑就双写。断言落在**真发件箱表 + 真投递器**上：
失败保行计次、换可用发布器后每条只成功一次、切回后已投递行不再重投。

`msg` 发布器在这里用「恒抛 `EventPublishError`」的替身表示不可达（真实网络失败在
`tests/msgclient/adapter/test_event_publisher.py` 已覆盖），这样这一条只验切换语义、不受网络影响。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope, EventPublisher, EventPublishError
from bms_core.models.outbox import SysOutbox
from bms_core.outbox.base import OUTBOX_STATUS_DELIVERED
from bms_core.outbox.dispatcher import PollOutboxDispatcher
from bms_core.outbox.store import SqlOutboxStore

pytestmark = pytest.mark.kiwi_id(2442)


class _RecordingPublisher(EventPublisher):
    """记录成功发布的事件（可用时）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型（测试固定）。"""
        return "msg"

    async def publish(self, event: EventEnvelope) -> None:
        """记录一条已投递事件。"""
        self.events.add(event)

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务发布（同 `publish`）。"""
        await self.publish(event)


class _UnreachablePublisher(EventPublisher):
    """恒抛 `EventPublishError` 的发布器（模拟 msg 实例不可达）。"""

    def __init__(self) -> None:
        """初始化。"""
        self.attempts: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型（测试固定）。"""
        return "msg"

    async def publish(self, event: EventEnvelope) -> None:
        """记录一次尝试后抛投递失败。

        Raises:
            EventPublishError: 恒定失败（10009）。
        """
        self.attempts.add(event.event_id or "")
        raise EventPublishError("msg 实例不可达（注入）")

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务发布（同 `publish`）。"""
        await self.publish(event)


def _dispatcher(registry: EngineRegistry, publisher: EventPublisher) -> PollOutboxDispatcher:
    """构造投递器（零退避，让「下一轮」在同一时刻就能取到失败行）。

    Args:
        registry: 引擎注册表。
        publisher: 事件发布端口（切换对象）。

    Returns:
        PollOutboxDispatcher: 投递器。
    """
    return PollOutboxDispatcher(
        store=SqlOutboxStore(),
        publisher=publisher,
        engine_registry=registry,
        session_factory=SessionFactory(),
        batch_size=100,
        max_retries=3,
        backoff=0.0,
        db_keys=ConcurrentStableList((PLATFORM_DB_KEY,)),
    )


async def test_unconfirmed_events_survive_switch_and_deliver_once(session: DbSession, registry: EngineRegistry) -> None:
    """未确认事件：旧 provider 不可达不丢，换新 provider 后每条只成功一次，切回不重投。"""
    store = SqlOutboxStore()
    async with session.begin():
        first = (
            await store.enqueue(
                session, EventEnvelope(event_type="order.created", payload=ConcurrentStableDict({"id": 1}))
            )
        ) or ""
        second = (
            await store.enqueue(
                session, EventEnvelope(event_type="order.paid", payload=ConcurrentStableDict({"id": 2}))
            )
        ) or ""

    # ① 切换前：msg 不可达 → 两条都失败，但行保留、失败计数递增（不丢）
    unreachable = _UnreachablePublisher()
    failed_round = await _dispatcher(registry, unreachable).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (failed_round.published, failed_round.failed, failed_round.dead) == (0, 2, 0)
    assert list(unreachable.attempts) == [first, second]
    async with session.begin():
        rows = (
            await session.execute(
                select(SysOutbox.event_id, SysOutbox.status, SysOutbox.retry_count, SysOutbox.error_msg)
            )
        ).all()
    assert {row.event_id for row in rows} == {first, second}
    assert all(row.status != OUTBOX_STATUS_DELIVERED for row in rows)
    assert all(row.retry_count == 1 and row.error_msg for row in rows)

    # ② 切到可用 provider：同一批发件箱行被补发，每条只成功一次（不双写）
    working = _RecordingPublisher()
    ok_round = await _dispatcher(registry, working).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (ok_round.published, ok_round.failed, ok_round.dead) == (2, 0, 0)
    delivered_ids = [event.event_id or "" for event in working.events]
    assert sorted(delivered_ids) == sorted([first, second])
    assert len(delivered_ids) == len(set(delivered_ids))

    # ③ 切回旧 provider：已投递行不再重投（不丢也不重复）
    back_round = await _dispatcher(registry, unreachable).dispatch_once(db_key=PLATFORM_DB_KEY)
    assert (back_round.published, back_round.failed) == (0, 0)
    assert list(unreachable.attempts) == [first, second]
    async with session.begin():
        statuses = (await session.execute(select(SysOutbox.status))).scalars().all()
    assert set(statuses) == {OUTBOX_STATUS_DELIVERED}
