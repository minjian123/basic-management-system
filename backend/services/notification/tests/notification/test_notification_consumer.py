"""通知组消费：渠道过滤 / 免打扰 / 推送 / 发件箱 / 毒消息（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import EventConsumeError
from bms_core.db.tenant import TenantContext
from bms_core.events.base import EventEnvelope
from bms_core.notification.preference import NotificationPreference, default_notification_preference
from bms_core.testing.transaction import rollback_session
from bms_core.ws.base import RealtimeEvent
from bms_notification.domains.notification.consumers import (
    NotificationRequestConsumer,
    event_consumer_records,
)
from bms_notification.domains.notification.models.mail import SysMailLog
from bms_notification.domains.notification.models.notification import SysNotification
from bms_notification.domains.notification.models.sms import SysSmsLog
from bms_notification.domains.notification.services.recipient import RecipientInfo
from notification._support import session_opener

pytestmark = pytest.mark.kiwi_id(2517)

_TENANT = TenantContext(code="demo", db_key="tenant_demo", name="演示", tenant_id=1001)


class _Lookup:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def by_id(self, tenant_id: str, *, readonly: bool = False) -> TenantContext:
        del tenant_id, readonly
        if self._fail:
            raise ValueError("bad tenant")
        return _TENANT


class _Outbox:
    def __init__(self) -> None:
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    async def enqueue(self, session: object, event: EventEnvelope) -> str:
        del session
        self.events.add(event)
        return f"evt-{len(self.events)}"


class _Realtime:
    def __init__(self, *, fail: bool = False) -> None:
        self.events: ConcurrentStableList[tuple[str, str | None]] = ConcurrentStableList()
        self._fail = fail

    async def emit(self, event: RealtimeEvent) -> None:
        if self._fail:
            raise RuntimeError("push down")
        self.events.add((event.event, event.user_id))

    async def join(self, session_id: str, room: str) -> None:
        del session_id, room

    async def leave(self, session_id: str, room: str) -> None:
        del session_id, room


class _Jobs:
    def __init__(self, *, fail: bool = False) -> None:
        self.submitted: ConcurrentStableList[tuple[str, str | None]] = ConcurrentStableList()
        self._fail = fail

    async def submit(
        self,
        session: object,
        *,
        job_type: str,
        payload: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> int:
        del session, tenant_id
        if self._fail:
            raise RuntimeError("job center down")
        self.submitted.add((job_type, str(payload.get("recipient"))))
        return len(self.submitted)


class _Resolver:
    def __init__(self, info: RecipientInfo | None = None, *, fail: bool = False) -> None:
        self.info = info or RecipientInfo(email="a@b.c", phone="13800000000", locale="zh-CN")
        self._fail = fail

    async def resolve(self, user_id: int) -> RecipientInfo:
        del user_id
        if self._fail:
            raise RuntimeError("platform down")
        return self.info


class _Preference:
    def __init__(self, pref: NotificationPreference | None = None, *, fail: bool = False) -> None:
        self._pref = pref or default_notification_preference()
        self._fail = fail

    async def load(self, user_id: int) -> NotificationPreference:
        del user_id
        if self._fail:
            raise RuntimeError("pref down")
        return self._pref


def _event(**overrides: object) -> EventEnvelope:
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {"user_id": "1", "title": "审批待办", "type": "approval", "content": "请处理", "biz_type": "approval"}
    )
    payload.update(overrides)
    return EventEnvelope(event_type="notification.requested", payload=payload, tenant_id="1001")


def _event_without_tenant() -> EventEnvelope:
    return EventEnvelope(
        event_type="notification.requested",
        payload=ConcurrentStableDict({"user_id": "1", "title": "x", "type": "system"}),
        tenant_id=None,
    )


def _consumer(
    session: object,
    *,
    pref: NotificationPreference | None = None,
    pref_fail: bool = False,
    realtime: _Realtime | None = None,
    jobs: _Jobs | None = None,
    resolver: _Resolver | None = None,
    outbox: _Outbox | None = None,
    lookup: _Lookup | None = None,
) -> NotificationRequestConsumer:
    return NotificationRequestConsumer(
        preference=cast("object", _Preference(pref, fail=pref_fail)),  # pyright: ignore[reportArgumentType]
        realtime=cast("object", realtime or _Realtime()),  # pyright: ignore[reportArgumentType]
        recipient_resolver=cast("object", resolver or _Resolver()),  # pyright: ignore[reportArgumentType]
        outbound_jobs=cast("object", jobs or _Jobs()),  # pyright: ignore[reportArgumentType]
        outbox=cast("object", outbox or _Outbox()),  # pyright: ignore[reportArgumentType]
        tenant_lookup=cast("object", lookup or _Lookup()),  # pyright: ignore[reportArgumentType]
        session_opener=lambda tenant: session_opener(session),  # pyright: ignore[reportArgumentType]
    )


async def test_inbox_and_push(shared_tenant_engine: AsyncEngine) -> None:
    """站内信落库 + notification.sent + notification.new / approval.todo。"""
    async with rollback_session(shared_tenant_engine) as session:
        outbox = _Outbox()
        realtime = _Realtime()
        await _consumer(session, outbox=outbox, realtime=realtime).consume(_event())
        row = (await session.execute(select(SysNotification))).scalars().one()
        assert row.user_id == 1
        assert row.type == "approval"
        assert [event.event_type for event in outbox.events] == ["notification.sent"]
        assert outbox.events[0].payload["biz_type"] == "approval"
        assert [item[0] for item in realtime.events] == ["notification.new", "approval.todo"]


async def test_without_biz_type(shared_tenant_engine: AsyncEngine) -> None:
    """无业务类型时不写 biz_type 字段。"""
    async with rollback_session(shared_tenant_engine) as session:
        outbox = _Outbox()
        await _consumer(session, outbox=outbox).consume(_event(type="system", biz_type=None))
        assert "biz_type" not in outbox.events[0].payload


async def test_non_approval_only_pushes_new(shared_tenant_engine: AsyncEngine) -> None:
    """非审批类只推 notification.new。"""
    async with rollback_session(shared_tenant_engine) as session:
        realtime = _Realtime()
        await _consumer(session, realtime=realtime).consume(_event(type="system"))
        assert [item[0] for item in realtime.events] == ["notification.new"]


async def test_quiet_hours_skips_push(shared_tenant_engine: AsyncEngine) -> None:
    """免打扰命中：落库但不推送。"""
    async with rollback_session(shared_tenant_engine) as session:
        realtime = _Realtime()
        pref = NotificationPreference(dnd_enabled=True, dnd_start="00:00", dnd_end="23:59", timezone="UTC")
        now = datetime.now(UTC)
        assert 0 <= now.hour <= 23
        await _consumer(session, pref=pref, realtime=realtime).consume(_event())
        assert (await session.execute(select(SysNotification))).scalars().one()
        assert realtime.events == []


async def test_inbox_disabled(shared_tenant_engine: AsyncEngine) -> None:
    """站内信渠道关闭：不落库、不发事件、不推送。"""
    async with rollback_session(shared_tenant_engine) as session:
        outbox = _Outbox()
        realtime = _Realtime()
        pref = NotificationPreference(channels=ConcurrentStableFrozenDict({"inbox": False, "email": True, "sms": True}))
        await _consumer(session, pref=pref, outbox=outbox, realtime=realtime).consume(_event())
        assert (await session.execute(select(SysNotification))).scalars().all() == []
        assert outbox.events == []
        assert realtime.events == []


async def test_external_channels(shared_tenant_engine: AsyncEngine) -> None:
    """邮件 / 短信按开关与地址经外发调度器落日志 + 提交作业；短信缺模板记失败。"""
    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        pref = NotificationPreference(channels=ConcurrentStableFrozenDict({"inbox": False, "email": True, "sms": True}))
        await _consumer(session, pref=pref, jobs=jobs).consume(_event(email="a@b.c", phone="13800000000"))
        mail = (await session.execute(select(SysMailLog))).scalars().one()
        assert mail.recipient == "a@b.c"
        assert mail.status == "pending"
        sms = (await session.execute(select(SysSmsLog))).scalars().one()
        assert sms.status == "failed"
        assert "template_code" in (sms.error_msg or "")
        assert [item[0] for item in jobs.submitted] == ["notification.mail.send"]


async def test_external_failure_and_pref_failure(shared_tenant_engine: AsyncEngine) -> None:
    """外发失败与偏好读取失败均不影响站内信。"""
    async with rollback_session(shared_tenant_engine) as session:
        pref = NotificationPreference(channels=ConcurrentStableFrozenDict({"inbox": True, "email": True, "sms": False}))
        await _consumer(session, pref=pref, resolver=_Resolver(fail=True)).consume(_event(email="a@b.c"))
        assert (await session.execute(select(SysNotification))).scalars().one()

    async with rollback_session(shared_tenant_engine) as session:
        await _consumer(session, pref_fail=True, realtime=_Realtime(fail=True)).consume(_event())
        assert (await session.execute(select(SysNotification))).scalars().one()


async def test_bad_payloads(shared_tenant_engine: AsyncEngine) -> None:
    """毒消息：缺字段 / 类型非法 / 超长 / 缺租户 / 租户不可解析。"""
    async with rollback_session(shared_tenant_engine) as session:
        consumer = _consumer(session)
        cases = (
            _event(user_id="x"),
            _event(title=""),
            _event(title="x" * 257),
            _event(type="bad"),
            _event(content=1),
            _event(content="x" * 10001),
            _event(biz_type=1),
            _event(biz_id="x" * 65),
            _event(email="x" * 129),
            _event(phone="x" * 33),
            _event(sms_template_code="x" * 65),
            _event(sms_params={"k": 1}),
            _event(sms_params={"k": "x" * 513}),
            _event(sms_params=[1]),
            EventEnvelope(event_type="notification.requested", payload=ConcurrentStableDict(), tenant_id=None),
        )
        for event in cases:
            with pytest.raises(EventConsumeError):
                await consumer.consume(event)

        with pytest.raises(EventConsumeError):
            await consumer.consume(_event_without_tenant())

        with pytest.raises(EventConsumeError):
            await _consumer(session, lookup=_Lookup(fail=True)).consume(_event())


def test_consumer_records() -> None:
    """消费组声明形态与事件类型。"""
    records = event_consumer_records()
    assert len(records) == 1
    record = records[0]
    assert record.consumer == "notification-inbox"
    assert record.event_type == "notification.requested"
    assert record.ordered is False
    handler = record.handler_factory()
    assert isinstance(handler, NotificationRequestConsumer)
    assert handler.event_type == "notification.requested"


async def test_default_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """生产默认装配：引擎注册表 / 租户源 / 会话 / 三个能力域解析。"""
    import bms_notification.domains.notification.consumers as module

    sentinel = object()
    monkeypatch.setattr(module, "EngineRegistry", lambda factory: sentinel)
    monkeypatch.setattr(module, "build_tenant_lookup", lambda *args, **kwargs: "lookup")
    module._registry_cache = None
    module._lookup_cache = None
    try:
        assert module._registry() is sentinel
        assert module._registry() is sentinel
        assert module._lookup() == "lookup"
        assert module._lookup() == "lookup"

        @asynccontextmanager
        async def fake_scope(*args: object, **kwargs: object) -> AsyncIterator[object]:
            yield "session"

        monkeypatch.setattr(module, "session_scope", fake_scope)
        opener = module._default_session_opener(_TENANT)
        async with opener as session:
            assert session == "session"

        monkeypatch.setattr(module, "resolve_plugin", lambda *args, **kwargs: sentinel)
        assert module._default_preference() is sentinel
        assert module._default_realtime() is sentinel

        class _Factory:
            def __init__(self, settings: object) -> None:
                del settings

            def create(self) -> object:
                return sentinel

        monkeypatch.setattr("bms_core.core.assembly.HttpServiceClientFactory", _Factory)
        module._recipient_resolver_cache = None
        resolver = module._default_recipient_resolver()
        assert resolver is module._default_recipient_resolver()
        module._recipient_resolver_cache = None
    finally:
        module._registry_cache = None
        module._lookup_cache = None
        module._recipient_resolver_cache = None
