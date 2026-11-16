"""BaseNotifier http 实现：受理 / 未受理 / 不可达 / 短信无模板。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import json

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.exceptions import ServiceUnavailableError
from bms_core.notify.base import NotificationMessage, NotifyChannel
from bms_core.notify.http import INTERNAL_SEND_PATH, HttpNotifier
from bms_core.servicecall.base import ServiceRequest, ServiceResponse

pytestmark = pytest.mark.kiwi_id(2519)


def test_factory_creates_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配工厂构造 HttpNotifier（注入服务客户端）。"""
    import bms_core.core.assembly as assembly

    client = _Client()

    def _fake_client(app: object) -> _Client:
        del app
        return client

    monkeypatch.setattr(assembly, "_resolve_service_client", _fake_client)
    factory = assembly.HttpNotifierFactory(app=object())  # type: ignore[arg-type]
    notifier = factory.create()
    assert isinstance(notifier, HttpNotifier)


class _Client:
    def __init__(
        self,
        *,
        status: int = 200,
        data: ConcurrentStableDict[str, object] | None = None,
        fail: bool = False,
        raw: bytes | None = None,
    ) -> None:
        self.status = status
        self.data = data or ConcurrentStableDict({"log_id": "1", "status": "pending"})
        self.fail = fail
        self.raw = raw
        self.requests: ConcurrentStableList[ServiceRequest] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        self.requests.add(request)
        if self.fail:
            raise ServiceUnavailableError("down")
        body = self.raw or json.dumps({"code": 0, "data": dict(self.data)}).encode()
        return ServiceResponse(status_code=self.status, content=body)


async def test_notifier_email_accepted() -> None:
    """邮件请求经内部端点受理，返回 log_id。"""
    client = _Client()
    result = await HttpNotifier(client=client).send(  # pyright: ignore[reportArgumentType]
        NotificationMessage(channel=NotifyChannel.EMAIL, recipient="a@b.c", content="hi", title="t")
    )
    assert result.delivered is True
    assert result.message_id == "1"
    request = client.requests[0]
    assert request.path == INTERNAL_SEND_PATH


async def test_notifier_sms_requires_template() -> None:
    """短信无模板不发起调用。"""
    client = _Client()
    result = await HttpNotifier(client=client).send(  # pyright: ignore[reportArgumentType]
        NotificationMessage(channel=NotifyChannel.SMS, recipient="13800000000", content="hi")
    )
    assert result.delivered is False
    assert client.requests == []


async def test_notifier_sms_with_template_and_skipped() -> None:
    """带模板短信发起调用；skipped 视为未送达。"""
    client = _Client(data=ConcurrentStableDict({"log_id": "2", "status": "skipped"}))
    result = await HttpNotifier(client=client).send(  # pyright: ignore[reportArgumentType]
        NotificationMessage(
            channel=NotifyChannel.SMS,
            recipient="13800000000",
            content="hi",
            template_code="sms_captcha",
            params=ConcurrentStableFrozenDict({"code": "1"}),
        )
    )
    assert result.delivered is False
    assert len(client.requests) == 1


async def test_notifier_inbox_and_invalid_payload() -> None:
    """站内信渠道不支持；响应非对象 / 缺 data 判未送达。"""
    inbox = await HttpNotifier(client=_Client()).send(  # pyright: ignore[reportArgumentType]
        NotificationMessage(channel=NotifyChannel.INBOX, recipient="1", content="hi")
    )
    assert inbox.delivered is False

    for raw in (b"[]", b'{"code":0,"data":1}'):
        invalid = await HttpNotifier(client=_Client(raw=raw)).send(  # pyright: ignore[reportArgumentType]
            NotificationMessage(channel=NotifyChannel.EMAIL, recipient="a@b.c", content="hi", title="t")
        )
        assert invalid.delivered is False


async def test_notifier_failures() -> None:
    """非 2xx / 不可达 / 响应非法均判未送达。"""
    for client in (
        _Client(status=500),
        _Client(fail=True),
        _Client(data=ConcurrentStableDict({"bad": "shape"})),
    ):
        result = await HttpNotifier(client=client).send(  # pyright: ignore[reportArgumentType]
            NotificationMessage(channel=NotifyChannel.EMAIL, recipient="a@b.c", content="hi", title="t")
        )
        assert result.delivered is False
