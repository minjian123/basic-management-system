"""投递器用例（Kiwi 2172）：转发与标记 / 顺序 / 重试死信 / 多库隔离 / 空实现 / 后台启停。

测试库：临时 SQLite（建发件箱三表）；事件发布用测试替身（真实发布归阶段十 M10）。
"""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from starlette.requests import Request

from bms_core.core.exceptions import OutboxDeliveryError
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.sync import DbSession
from bms_core.events.base import EventEnvelope, EventPublisher
from bms_core.metrics.base import BaseMetrics, MetricLabels
from bms_core.models.outbox import SysEventDeadLetter, SysOutbox
from bms_core.outbox import base as outbox_base
from bms_core.outbox.base import (
    OUTBOX_STATUS_DEAD,
    OUTBOX_STATUS_DELIVERED,
    BaseOutboxDispatcher,
    BaseOutboxStore,
    DeadLetterRecord,
    DispatchResult,
    OutboxRecord,
)
from bms_core.outbox.dispatcher import PollOutboxDispatcher
from bms_core.outbox.null import NullOutboxDispatcher, NullOutboxStore
from bms_core.outbox.store import SqlOutboxStore


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。"""
    return datetime.now(UTC).replace(tzinfo=None)


class RecordingPublisher(EventPublisher):
    """记录发布事件（可指定失败类型）。"""

    def __init__(self, *, fail_types: frozenset[str] = frozenset()) -> None:
        """初始化。

        Args:
            fail_types: 触发发布失败的事件类型集合。
        """
        self.events: list[EventEnvelope] = []
        self._fail_types = fail_types

    @property
    def event_type(self) -> str:
        """事件类型（测试固定）。"""
        return "test.probe"

    async def publish(self, event: EventEnvelope) -> None:
        """记录并可按类型抛错。"""
        self.events.append(event)
        if event.event_type in self._fail_types:
            raise RuntimeError("publish failed")

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务发布（同 `publish`）。"""
        await self.publish(event)


class RecordingMetrics(BaseMetrics):
    """记录指标调用。"""

    def __init__(self) -> None:
        """初始化。"""
        self.counters: list[tuple[str, float, Mapping[str, str] | None]] = []
        self.gauges: list[tuple[str, float]] = []

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        """记录计数器。"""
        self.counters.append((name, value, labels))

    async def gauge(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录瞬时值。"""
        del labels
        self.gauges.append((name, value))

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        """记录直方图（未使用）。"""
        del name, value, labels


class BrokenStore(BaseOutboxStore):
    """取待投递抛错的存储替身。"""

    async def enqueue(self, session: DbSession, event: EventEnvelope) -> str:
        """不实现（测试用）。"""
        return ""

    async def claim_pending(self, session: DbSession, *, now: datetime, limit: int) -> list[OutboxRecord]:
        """恒定抛错。"""
        raise RuntimeError("store down")

    async def mark_delivered(self, session: DbSession, event_id: str) -> None:
        """不实现（测试用）。"""

    async def mark_failed(
        self, session: DbSession, event_id: str, error: str, *, max_retries: int, backoff: float
    ) -> bool:
        """不实现（测试用）。"""
        return False

    async def replay(
        self,
        session: DbSession,
        *,
        event_id: str | None = None,
        event_type: str | None = None,
        aggregate_key: str | None = None,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> int:
        """不实现（测试用）。"""
        return 0

    async def list_dead_letters(
        self,
        session: DbSession,
        *,
        status: str | None = None,
        source: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[DeadLetterRecord], int]:
        """不实现（测试用）。"""
        return [], 0

    async def get_dead_letter(self, session: DbSession, dead_letter_id: int) -> DeadLetterRecord | None:
        """不实现（测试用）。"""
        return None

    async def set_dead_letter_status(self, session: DbSession, dead_letter_id: int, status: str) -> bool:
        """不实现（测试用）。"""
        return False

    async def backlog(self, session: DbSession) -> int:
        """不实现（测试用）。"""
        return 0


def _build_dispatcher(
    registry: EngineRegistry,
    publisher: EventPublisher,
    *,
    store: BaseOutboxStore | None = None,
    metrics: BaseMetrics | None = None,
    max_retries: int = 3,
    enabled: bool = False,
    interval: float = 3600.0,
) -> PollOutboxDispatcher:
    """构造投递器（测试辅助）。"""
    return PollOutboxDispatcher(
        store=store or SqlOutboxStore(),
        publisher=publisher,
        engine_registry=registry,
        session_factory=SessionFactory(),
        batch_size=100,
        max_retries=max_retries,
        backoff=1.0,
        db_keys=(PLATFORM_DB_KEY,),
        interval=interval,
        metrics=metrics,
        enabled=enabled,
    )


class ErrorStore(BrokenStore):
    """取待投递抛 `OutboxDeliveryError` 的存储替身（验证投递器原样上抛）。"""

    async def claim_pending(self, session: DbSession, *, now: datetime, limit: int) -> list[OutboxRecord]:
        """恒定抛 `OutboxDeliveryError`。"""
        raise OutboxDeliveryError("store advance error")


class BoomDispatcher(PollOutboxDispatcher):
    """单轮轮询恒抛异常（验证后台循环不终止）。"""

    async def dispatch_due(self) -> DispatchResult:
        """恒定抛错。"""
        raise RuntimeError("round boom")


@pytest.mark.kiwi_id(2172)
async def test_dispatch_marks_delivered_and_metrics(session: DbSession, registry: EngineRegistry) -> None:
    """投递转发 + 标记已投递 + 指标上报。"""
    store = SqlOutboxStore()
    async with session.begin():
        await store.enqueue(session, EventEnvelope(event_type="order.created", payload={"id": 1}))
        await store.enqueue(session, EventEnvelope(event_type="order.paid", tenant_id="t1"))
    publisher = RecordingPublisher()
    metrics = RecordingMetrics()
    dispatcher = _build_dispatcher(registry, publisher, metrics=metrics)

    result = await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)
    assert result.published == 2 and result.failed == 0 and result.dead == 0
    assert [event.event_type for event in publisher.events] == ["order.created", "order.paid"]
    async with session.begin():
        statuses = (await session.execute(select(SysOutbox.status))).scalars().all()
    assert set(statuses) == {OUTBOX_STATUS_DELIVERED}
    assert ("bms_outbox_delivery_total", 2.0, {"status": "delivered"}) in metrics.counters
    assert metrics.gauges == [("bms_outbox_backlog", 0.0)]


@pytest.mark.kiwi_id(2172)
async def test_dispatch_preserves_aggregate_order(session: DbSession, registry: EngineRegistry) -> None:
    """同聚合按序投递：每轮仅队首，跨轮保持顺序。"""
    store = SqlOutboxStore()
    async with session.begin():
        first = await store.enqueue(session, EventEnvelope(event_type="e.a", aggregate_key="A"))
        second = await store.enqueue(session, EventEnvelope(event_type="e.a", aggregate_key="A"))
    publisher = RecordingPublisher()
    dispatcher = _build_dispatcher(registry, publisher)

    await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)
    assert [event.event_id for event in publisher.events] == [first]
    await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)
    assert [event.event_id for event in publisher.events] == [first, second]


@pytest.mark.kiwi_id(2172)
async def test_dispatch_failure_to_dead_letter(session: DbSession, registry: EngineRegistry) -> None:
    """发布失败：退避重试、超上限转死信并插死信行。"""
    store = SqlOutboxStore()
    async with session.begin():
        await store.enqueue(session, EventEnvelope(event_type="e.fail", tenant_id="t1"))
    publisher = RecordingPublisher(fail_types=frozenset({"e.fail"}))
    dispatcher = _build_dispatcher(registry, publisher, max_retries=1)

    result = await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)
    assert result.failed == 1 and result.dead == 1 and result.published == 0
    async with session.begin():
        row = (await session.execute(select(SysOutbox))).scalars().one()
        assert row.status == OUTBOX_STATUS_DEAD
        letters = (await session.execute(select(func.count()).select_from(SysEventDeadLetter))).scalar_one()
    assert letters == 1


@pytest.mark.kiwi_id(2172)
async def test_dispatch_due_isolates_broken_db(session: DbSession, registry: EngineRegistry) -> None:
    """多库轮询：单库异常隔离，其余继续；合并汇总。"""
    store = SqlOutboxStore()
    async with session.begin():
        await store.enqueue(session, EventEnvelope(event_type="e.ok"))
    publisher = RecordingPublisher()
    dispatcher = PollOutboxDispatcher(
        store=store,
        publisher=publisher,
        engine_registry=registry,
        session_factory=SessionFactory(),
        db_keys=(PLATFORM_DB_KEY, "tenant_missing"),
        interval=3600.0,
    )
    result = await dispatcher.dispatch_due()
    assert result.published == 1
    assert [event.event_type for event in publisher.events] == ["e.ok"]


@pytest.mark.kiwi_id(2172)
async def test_dispatch_store_error_raises(registry: EngineRegistry) -> None:
    """存储异常：抛 `OutboxDeliveryError`（10009）。"""
    dispatcher = _build_dispatcher(registry, RecordingPublisher(), store=BrokenStore())
    with pytest.raises(OutboxDeliveryError):
        await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)


@pytest.mark.kiwi_id(2172)
async def test_dispatch_lifecycle_and_null(registry: EngineRegistry, session: DbSession) -> None:
    """后台启停（enabled）；空实现无副作用。"""
    dispatcher = _build_dispatcher(registry, RecordingPublisher(), enabled=True)
    assert dispatcher.enabled is True
    await dispatcher.setup()
    assert getattr(dispatcher, "_task", None) is not None
    await dispatcher.aclose()
    assert getattr(dispatcher, "_task", None) is None
    await dispatcher.aclose()  # 幂等

    disabled = _build_dispatcher(registry, RecordingPublisher(), enabled=False)
    await disabled.setup()
    assert disabled.enabled is False and getattr(disabled, "_task", None) is None
    await disabled.aclose()

    null_store = NullOutboxStore()
    assert await null_store.enqueue(session, EventEnvelope(event_type="x")) == ""
    assert await null_store.claim_pending(session, now=_utc_now(), limit=10) == []
    await null_store.mark_delivered(session, "x")
    assert await null_store.mark_failed(session, "x", "e", max_retries=1, backoff=1) is False
    assert await null_store.replay(session) == 0
    assert await null_store.list_dead_letters(session) == ([], 0)
    assert await null_store.get_dead_letter(session, 1) is None
    assert await null_store.set_dead_letter_status(session, 1, "ignored") is False
    assert await null_store.backlog(session) == 0

    null_dispatcher = NullOutboxDispatcher()
    assert null_dispatcher.enabled is False
    assert await null_dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY) == DispatchResult()
    assert await null_dispatcher.dispatch_due() == DispatchResult()
    await null_dispatcher.setup()
    await null_dispatcher.aclose()
    assert isinstance(null_dispatcher, BaseOutboxDispatcher)


@pytest.mark.kiwi_id(2172)
async def test_dispatch_rethrows_and_due_isolates(registry: EngineRegistry) -> None:
    """投递器原样上抛 `OutboxDeliveryError`；`dispatch_due` 单库异常隔离。"""
    dispatcher = _build_dispatcher(registry, RecordingPublisher(), store=ErrorStore())
    with pytest.raises(OutboxDeliveryError):
        await dispatcher.dispatch_once(db_key=PLATFORM_DB_KEY)
    assert await dispatcher.dispatch_due() == DispatchResult()


@pytest.mark.kiwi_id(2172)
async def test_run_forever_loop(registry: EngineRegistry) -> None:
    """后台轮询循环运行一轮后取消退出。"""
    dispatcher = _build_dispatcher(registry, RecordingPublisher(), enabled=True, interval=0.01)
    await dispatcher.setup()
    await asyncio.sleep(0.05)
    await dispatcher.aclose()


@pytest.mark.kiwi_id(2172)
async def test_run_forever_survives_round_error(registry: EngineRegistry) -> None:
    """单轮异常不终止后台循环（记日志后继续）。"""
    dispatcher = BoomDispatcher(
        store=SqlOutboxStore(),
        publisher=RecordingPublisher(),
        engine_registry=registry,
        session_factory=SessionFactory(),
        db_keys=(PLATFORM_DB_KEY,),
        interval=0.01,
        enabled=True,
    )
    await dispatcher.setup()
    await asyncio.sleep(0.05)
    await dispatcher.aclose()


def test_providers_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入提供者按配置解析（装配 settings → `resolve_plugin`）。"""
    sentinel = object()

    def _fake_resolve(plugin_key: str, provider: str = "", *, expected_version: str = "") -> object:
        del plugin_key, provider, expected_version
        return sentinel

    monkeypatch.setattr(outbox_base, "resolve_plugin", _fake_resolve)
    settings = SimpleNamespace(
        outbox=SimpleNamespace(provider="poll"),
        outbox_store=SimpleNamespace(provider="sql"),
    )
    app = FastAPI()
    app.state.settings = settings
    request = Request({"type": "http", "app": app, "headers": []})
    assert outbox_base.get_outbox_store(request) is sentinel
    assert outbox_base.get_outbox_dispatcher(request) is sentinel
