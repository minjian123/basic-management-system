"""通知渠道基座契约测试（Kiwi 50）：契约 / 标识 / 渠道枚举 / 数据契约 / 占位固定成功 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_notifier
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import ApplicationFactory, lifespan
from app.notify.base import NULL_MESSAGE_ID, BaseNotifier, NotificationMessage, NotifyChannel, SendResult
from app.notify.null import NullNotifier


@pytest.mark.kiwi_id(50)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseNotifier, BaseCapability)
    assert issubclass(NullNotifier, BaseNotifier)
    assert issubclass(NullNotifier, BaseNullObject)
    assert BaseNotifier.key == "notifier"

    notifier = NullNotifier()
    assert notifier.placeholder is True
    assert "占位实现" in notifier.describe()


@pytest.mark.kiwi_id(50)
def test_channel_enum() -> None:
    """渠道枚举三值（StrEnum 字符串比较）。"""
    assert [channel.value for channel in NotifyChannel] == ["inbox", "email", "sms"]
    assert NotifyChannel.INBOX == "inbox"
    assert NotifyChannel.EMAIL == "email"
    assert NotifyChannel.SMS == "sms"


@pytest.mark.kiwi_id(50)
def test_data_contracts_defaults_and_frozen() -> None:
    """`NotificationMessage` / `SendResult` 默认值正确且不可变。"""
    message = NotificationMessage(channel=NotifyChannel.INBOX, recipient="1", content="hi")
    assert message.title == ""
    assert message.biz_type is None
    assert message.biz_id is None
    assert SendResult(delivered=True).message_id is None
    assert SendResult(delivered=True).detail is None

    field = "content"
    with pytest.raises(FrozenInstanceError):
        setattr(message, field, "other")


@pytest.mark.kiwi_id(50)
async def test_null_send_fixed_success() -> None:
    """占位发送恒定成功（不真实发送）。"""
    notifier = NullNotifier()
    message = NotificationMessage(channel=NotifyChannel.EMAIL, recipient="a@b.c", content="hi")
    result = await notifier.send(message)
    assert result == SendResult(delivered=True, message_id=NULL_MESSAGE_ID)
    assert result.delivered is True


@pytest.mark.kiwi_id(50)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位通知器；路由经 get_notifier 取到同一实例。"""
    app = ApplicationFactory().create(None)
    async with lifespan(app):
        assert isinstance(app.state.notifier, NullNotifier)

        @app.get("/notify-probe")
        async def probe(  # pyright: ignore[reportUnusedFunction]
            notifier: Annotated[BaseNotifier, Depends(get_notifier)],
        ) -> dict[str, object]:
            result = await notifier.send(NotificationMessage(channel=NotifyChannel.INBOX, recipient="1", content="hi"))
            return {"key": notifier.key, "type": type(notifier).__name__, "delivered": result.delivered}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/notify-probe")

        assert resp.status_code == 200
        assert resp.json() == {"key": "notifier", "type": "NullNotifier", "delivered": True}
