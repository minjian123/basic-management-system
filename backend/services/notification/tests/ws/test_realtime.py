"""实时推送基座契约测试（Kiwi 51）：契约 / 标识 / 事件常量 / 数据契约 / 占位空操作 / 依赖解析。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.ws.base import REALTIME_EVENTS, BaseRealtimePublisher, RealtimeEvent
from bms_core.ws.null import NullRealtimePublisher


@pytest.mark.kiwi_id(51)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseRealtimePublisher, BaseCapability)
    assert issubclass(NullRealtimePublisher, BaseRealtimePublisher)
    assert issubclass(NullRealtimePublisher, BaseNullObject)
    assert BaseRealtimePublisher.key == "realtime_publisher"

    publisher = NullRealtimePublisher()
    assert publisher.placeholder is True
    assert "占位实现" in publisher.describe()


@pytest.mark.kiwi_id(51)
def test_event_constants() -> None:
    """事件常量清单三项无重复。"""
    assert REALTIME_EVENTS == ("approval.todo", "notification.new", "session.revoked")
    assert len(set(REALTIME_EVENTS)) == len(REALTIME_EVENTS)


@pytest.mark.kiwi_id(51)
def test_data_contract_defaults_and_frozen() -> None:
    """`RealtimeEvent` 目标字段默认值与不可变。"""
    event = RealtimeEvent(event="notification.new", data=ConcurrentStableFrozenDict({"id": "1"}))
    assert event.user_id is None
    assert event.session_id is None
    assert event.room is None

    field = "event"
    with pytest.raises(FrozenInstanceError):
        setattr(event, field, "other")


@pytest.mark.kiwi_id(51)
async def test_null_publisher_noop() -> None:
    """占位三方法空操作（不连 Socket.IO / Redis）。"""
    publisher = NullRealtimePublisher()
    assert (
        await publisher.emit(
            RealtimeEvent(event="notification.new", data=ConcurrentStableFrozenDict[str, object](), user_id="1")
        )
        is None
    )
    assert await publisher.join("sess-1", "room-1") is None
    assert await publisher.leave("sess-1", "room-1") is None


@pytest.mark.kiwi_id(51)
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态推送器是占位实现，提供者与本应用一致。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    publisher = service_app.state.realtime_publisher
    assert isinstance(publisher, NullRealtimePublisher)
    assert service_app.state.plugin_providers["realtime_publisher"] == "null"
    assert (
        await publisher.emit(
            RealtimeEvent(event="notification.new", data=ConcurrentStableFrozenDict[str, object](), user_id="1")
        )
        is None
    )
