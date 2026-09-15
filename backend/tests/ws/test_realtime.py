"""实时推送基座契约测试（Kiwi 51）：契约 / 标识 / 事件常量 / 数据契约 / 占位空操作 / 依赖解析。"""

from dataclasses import FrozenInstanceError
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_realtime_publisher
from app.core.base import BaseObject
from app.core.capability import BaseCapability, BaseNullObject
from app.main import create_app
from app.ws.base import REALTIME_EVENTS, BaseRealtimePublisher, RealtimeEvent
from app.ws.null import NullRealtimePublisher


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
    event = RealtimeEvent(event="notification.new", data={"id": "1"})
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
    assert await publisher.emit(RealtimeEvent(event="notification.new", data={}, user_id="1")) is None
    assert await publisher.join("sess-1", "room-1") is None
    assert await publisher.leave("sess-1", "room-1") is None


@pytest.mark.kiwi_id(51)
async def test_dependency_provider_resolves() -> None:
    """依赖解析：应用装配占位推送器；路由经 get_realtime_publisher 取到同一实例。"""
    app = create_app()
    assert isinstance(app.state.realtime_publisher, NullRealtimePublisher)

    @app.get("/realtime-probe")
    async def probe(  # pyright: ignore[reportUnusedFunction]
        publisher: Annotated[BaseRealtimePublisher, Depends(get_realtime_publisher)],
    ) -> dict[str, object]:
        await publisher.emit(RealtimeEvent(event="notification.new", data={}, user_id="1"))
        return {"key": publisher.key, "type": type(publisher).__name__}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/realtime-probe")

    assert resp.status_code == 200
    assert resp.json() == {"key": "realtime_publisher", "type": "NullRealtimePublisher"}
