"""内部发送端点：邮件 raw / 短信模板 / 参数校验 / 未生成记录。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_notification.domains.notification.api.internal_send import internal_send
from bms_notification.domains.notification.schemas.internal_send import InternalSendRequest
from bms_notification.domains.notification.services.outbound import DispatchOutcome

pytestmark = pytest.mark.kiwi_id(2519)


class _Uow:
    session = object()

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        yield None


class _Dispatcher:
    def __init__(self, outcome: DispatchOutcome | None = None) -> None:
        self.outcome = outcome or DispatchOutcome(log_id=1, status="pending")
        self.requests: ConcurrentStableList[object] = ConcurrentStableList()

    async def dispatch(self, request: object, *, preference: object | None = None) -> DispatchOutcome:
        del preference
        self.requests.add(request)
        return self.outcome


async def test_internal_email_and_sms() -> None:
    """邮件 raw 受理；短信缺模板拒绝。"""
    dispatcher = _Dispatcher()
    response = await internal_send(
        _Uow(),  # pyright: ignore[reportArgumentType]
        dispatcher,  # pyright: ignore[reportArgumentType]
        InternalSendRequest(channel="email", recipient="a@b.c", title="t", content="hi"),
    )
    assert response.data.log_id == 1  # type: ignore[union-attr]

    with pytest.raises(ParamError):
        await internal_send(
            _Uow(),  # pyright: ignore[reportArgumentType]
            dispatcher,  # pyright: ignore[reportArgumentType]
            InternalSendRequest(channel="sms", recipient="13800000000", content="hi"),
        )


async def test_internal_sms_with_template() -> None:
    """短信带模板与参数。"""
    dispatcher = _Dispatcher()
    response = await internal_send(
        _Uow(),  # pyright: ignore[reportArgumentType]
        dispatcher,  # pyright: ignore[reportArgumentType]
        InternalSendRequest(
            channel="sms",
            recipient="13800000000",
            template_code="sms_captcha",
            params=ConcurrentStableDict({"code": "1"}),
        ),
    )
    assert response.data.status == "pending"  # type: ignore[union-attr]
    assert len(dispatcher.requests) == 1


async def test_internal_no_record() -> None:
    """未生成记录按参数错误。"""
    with pytest.raises(ParamError):
        await internal_send(
            _Uow(),  # pyright: ignore[reportArgumentType]
            _Dispatcher(DispatchOutcome(log_id=None, status="filtered")),  # pyright: ignore[reportArgumentType]
            InternalSendRequest(channel="email", recipient="a@b.c", content="hi"),
        )
