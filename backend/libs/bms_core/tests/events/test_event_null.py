"""事件基座占位护栏：发布 / 消费 Null 实现契约（Kiwi 689）。

依据《后端基类清单》「能力域横切」节（事件发布 / 消费）与《架构设计 · 事件总线》「同步 / 异步判定」节：
占位实现为空操作——不连消息中间件、不投递、不消费；真实实现随阶段十（M10 集成消息可用）回补。
"""

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request

import bms_core.events.base as events_base
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.events.base import (
    EventConsumer,
    EventEnvelope,
    EventPublisher,
    get_event_publisher,
)
from bms_core.events.null import NULL_EVENT_TYPE, NullEventConsumer, NullEventPublisher


@pytest.mark.kiwi_id(689)
async def test_null_publisher_publish_is_noop() -> None:
    """占位发布：`publish` / `publish_transactional` 均为空操作，`event_type` 取占位值。"""
    publisher = NullEventPublisher()
    event = EventEnvelope(event_type="sys.user.created", payload=ConcurrentStableDict({"id": 1}))
    assert publisher.event_type == NULL_EVENT_TYPE
    assert await publisher.publish(event) is None
    assert await publisher.publish_transactional(event) is None


@pytest.mark.kiwi_id(689)
async def test_null_consumer_consume_is_noop() -> None:
    """占位消费：`consume` 为空操作，`event_type` 取占位值（与发布侧对称）。"""
    consumer = NullEventConsumer()
    event = EventEnvelope(event_type="sys.user.created", payload=ConcurrentStableDict({"id": 1}))
    assert consumer.event_type == NULL_EVENT_TYPE
    assert await consumer.consume(event) is None


@pytest.mark.kiwi_id(689)
def test_null_implementations_satisfy_contracts() -> None:
    """占位实现满足发布 / 消费契约（真实实现随阶段十替换，业务代码零改动）。"""
    assert isinstance(NullEventPublisher(), EventPublisher)
    assert isinstance(NullEventConsumer(), EventConsumer)


@pytest.mark.kiwi_id(689)
def test_get_event_publisher_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """依赖注入提供者：按配置解析应用级发布实例（不触发进程级插件注册表构建）。"""
    resolved: ConcurrentStableList[tuple[str, str | None, str | None]] = ConcurrentStableList()

    def _fake_resolve(plugin_key: str, provider: str | None = None, *, expected_version: str | None = None) -> object:
        """替身：记录解析入参并返回占位发布实现。"""
        resolved.add((plugin_key, provider, expected_version))
        return NullEventPublisher()

    monkeypatch.setattr(events_base, "resolve_plugin", _fake_resolve)
    settings = get_settings()
    settings.event.provider = "kafka"
    request = cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))

    publisher = get_event_publisher(request)
    assert isinstance(publisher, NullEventPublisher)
    assert resolved == [("event", "kafka", EventPublisher.contract_version)]
