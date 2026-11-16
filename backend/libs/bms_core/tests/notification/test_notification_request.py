"""通知请求事件：负载 / 信封 / 租户位 / 发件箱助手（Kiwi 2517）。"""

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportDeprecated=false, reportUntypedFunctionDecorator=false, reportCallIssue=false
from __future__ import annotations

from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import reset_current_tenant_id, set_current_tenant_id
from bms_core.core.exceptions import ParamError
from bms_core.events.base import EventEnvelope
from bms_core.notification.request import (
    NOTIFICATION_REQUESTED_EVENT,
    NOTIFICATION_TYPE_APPROVAL,
    NOTIFICATION_TYPE_SYSTEM,
    NOTIFICATION_TYPES,
    NotificationRequest,
    _default_outbox,
    build_requested_envelope,
    enqueue_notification_request,
)
from bms_core.outbox.base import BaseOutboxStore

pytestmark = pytest.mark.kiwi_id(2517)


class _Outbox:
    """发件箱替身（只记录事件）。"""

    def __init__(self) -> None:
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()

    async def enqueue(self, session: object, event: EventEnvelope) -> str:
        del session
        self.events.add(event)
        return f"evt-{len(self.events)}"


def test_types_are_fixed() -> None:
    """四类通知类型固定且无重复。"""
    assert NOTIFICATION_TYPES == ("system", "approval", "alert", "import")
    assert len(set(NOTIFICATION_TYPES)) == 4


def test_payload_omits_empty_optional_fields() -> None:
    """负载只写非空可选字段。"""
    payload = NotificationRequest(user_id=1001, title="待办").to_payload()
    assert payload == {"user_id": "1001", "title": "待办", "type": NOTIFICATION_TYPE_SYSTEM}

    full = NotificationRequest(
        user_id=1001,
        title="审批",
        type=NOTIFICATION_TYPE_APPROVAL,
        content="请处理",
        biz_type="approval",
        biz_id="9",
        email="a@b.c",
        phone="13800000000",
    ).to_payload()
    assert full["content"] == "请处理"
    assert full["biz_type"] == "approval"
    assert full["biz_id"] == "9"
    assert full["email"] == "a@b.c"
    assert full["phone"] == "13800000000"


def test_envelope_has_type_tenant_and_aggregate_key() -> None:
    """信封带事件名 / 租户位 / 按用户聚合键 / 版本。"""
    envelope = build_requested_envelope(
        NotificationRequest(user_id=1001, title="待办"), tenant_id="2002"
    )
    assert envelope.event_type == NOTIFICATION_REQUESTED_EVENT
    assert envelope.tenant_id == "2002"
    assert envelope.aggregate_key == "notification:1001"
    assert envelope.event_version == "1.0.0"


def test_invalid_type_or_empty_title_rejected() -> None:
    """非法类型 / 空标题 / 缺租户位拒绝。"""
    with pytest.raises(ParamError):
        build_requested_envelope(NotificationRequest(user_id=1, title="x", type="bad"), tenant_id="2")
    with pytest.raises(ParamError):
        build_requested_envelope(NotificationRequest(user_id=1, title="  "), tenant_id="2")
    with pytest.raises(ParamError):
        build_requested_envelope(NotificationRequest(user_id=1, title="x"), tenant_id=None)


def test_tenant_id_falls_back_to_context() -> None:
    """未显式传租户时取当前上下文。"""
    token = set_current_tenant_id("3003")
    try:
        envelope = build_requested_envelope(NotificationRequest(user_id=1, title="x"), tenant_id=None)
    finally:
        reset_current_tenant_id(token)
    assert envelope.tenant_id == "3003"


async def test_enqueue_uses_given_outbox() -> None:
    """发件箱助手把事件交给注入实现。"""
    outbox = _Outbox()
    event_id = await enqueue_notification_request(
        object(),  # pyright: ignore[reportArgumentType]
        NotificationRequest(user_id=1001, title="待办"),
        tenant_id="2002",
        outbox=cast("BaseOutboxStore", outbox),
    )
    assert event_id == "evt-1"
    assert outbox.events[0].event_type == NOTIFICATION_REQUESTED_EVENT


def test_default_outbox_is_sql() -> None:
    """缺省发件箱为 SQL 实现。"""
    from bms_core.outbox.store import SqlOutboxStore

    assert isinstance(_default_outbox(), SqlOutboxStore)


def test_event_contract_payload_keys() -> None:
    """事件契约字段与请求负载一致。"""
    from bms_core.events.platform_events import PLATFORM_EVENT_CONTRACTS

    contract = next(item for item in PLATFORM_EVENT_CONTRACTS if item.event_type == NOTIFICATION_REQUESTED_EVENT)
    assert set(contract.fields) == {
        "user_id",
        "title",
        "type",
        "content",
        "biz_type",
        "biz_id",
        "email",
        "phone",
    }
    assert contract.version == "1.0.0"
