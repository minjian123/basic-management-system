"""通知渠道基座契约测试（Kiwi 50）：契约 / 标识 / 渠道枚举 / 数据契约 / 占位固定成功 / 依赖解析。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.notify.base import NULL_MESSAGE_ID, BaseNotifier, NotificationMessage, NotifyChannel, SendResult
from bms_core.notify.null import NullNotifier


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
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态通知器是占位实现（`delivered=True`），提供者与本应用一致。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    notifier = service_app.state.notifier
    assert isinstance(notifier, NullNotifier)
    assert service_app.state.plugin_providers["notifier"] == "null"
    result = await notifier.send(NotificationMessage(channel=NotifyChannel.INBOX, recipient="1", content="hi"))
    assert result.delivered is True
