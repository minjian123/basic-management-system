"""事件通道编码护栏：topic 派生与信封编解码（纯函数）。

依据《详细设计 · 事件总线》§4.1：
- topic = `bms.{事件域}.{对象}`（事件名前两段）——同对象多动作落同一 topic，订阅仍按事件类型精确匹配；
- 消息体为完整信封 JSON，属性冗余关键字段（属性优先、缺失回落 body）；
- 毒消息（非法 JSON / 缺幂等键 / 事件类型非法 / 负载非对象 / 时间非法）一律抛 `EventConsumeError`，
  消费组据此不重试、直接死信（重试只会阻塞同 key 队列）。
"""

from datetime import UTC, datetime

import pytest

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import EventConsumeError
from bms_core.events.base import EventEnvelope
from bms_core.events.topic import (
    ATTR_EVENT_ID,
    ATTR_EVENT_TYPE,
    ATTR_OCCURRED_AT,
    ATTR_TENANT_ID,
    ATTR_TRACEPARENT,
    decode_event,
    encode_event,
    event_attributes,
    topic_for,
)


def test_topic_for_takes_domain_and_object() -> None:
    """topic 取事件名前两段：动作不进 topic。"""
    assert topic_for("sys.user.created") == "bms.sys.user"
    assert topic_for("sys.user.updated") == "bms.sys.user"
    assert topic_for("wf.task.completed") == "bms.wf.task"


def test_topic_for_two_segment_event() -> None:
    """两段事件名全取（域 + 事件），与架构示例同形。"""
    assert topic_for("notification.sent") == "bms.notification.sent"


def test_topic_for_rejects_invalid_event_type() -> None:
    """非法事件名（段数不足 / 大写 / 首字符非字母）无法派生 topic。"""
    for invalid in ("sys", "Sys.User.Created", "1sys.user.created", ""):
        with pytest.raises(EventConsumeError):
            topic_for(invalid)


def test_encode_decode_round_trip() -> None:
    """编解码往返保真：信封八个字段逐一还原（含契约版本与聚合键）。"""
    occurred_at = datetime(2026, 10, 31, 2, 0, 0)
    event = EventEnvelope(
        event_type="wf.task.completed",
        payload=ConcurrentStableDict({"task_id": "t-1", "意见": "同意"}),
        tenant_id="1234567890",
        trace_id="a" * 32,
        event_id="evt-1",
        occurred_at=occurred_at,
        aggregate_key="1234567890",
        event_version="1.2.0",
    )
    decoded = decode_event(encode_event(event), event_attributes(event))
    assert decoded.event_type == "wf.task.completed"
    assert decoded.event_id == "evt-1"
    assert decoded.tenant_id == "1234567890"
    assert decoded.trace_id == "a" * 32
    assert decoded.aggregate_key == "1234567890"
    assert decoded.event_version == "1.2.0"
    assert decoded.occurred_at == occurred_at
    assert dict(decoded.payload) == {"task_id": "t-1", "意见": "同意"}


def test_attributes_omit_empty_values() -> None:
    """空值不落属性（避免消费端把空串当值），事件 ID / 类型 / 时间必在。"""
    event = EventEnvelope(event_type="sys.user.created", event_id="evt-2")
    attrs = event_attributes(event)
    assert attrs[ATTR_EVENT_ID] == "evt-2"
    assert attrs[ATTR_EVENT_TYPE] == "sys.user.created"
    assert ATTR_OCCURRED_AT in attrs
    assert ATTR_TENANT_ID not in attrs


def test_attributes_carry_traceparent() -> None:
    """有 OTel 时透传 W3C 链路上下文。"""
    event = EventEnvelope(event_type="sys.user.created", event_id="evt-3")
    attrs = event_attributes(event, traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
    assert ATTR_TRACEPARENT in attrs


def test_decode_prefers_attributes_over_body() -> None:
    """属性优先：属性与 body 冲突时以属性为准（属性是 broker 侧过滤依据）。"""
    body = encode_event(EventEnvelope(event_type="sys.user.created", event_id="from-body"))
    decoded = decode_event(
        body, ConcurrentStableDict({ATTR_EVENT_ID: "from-attr", ATTR_EVENT_TYPE: "sys.user.created"})
    )
    assert decoded.event_id == "from-attr"


def test_decode_without_attributes_falls_back_to_body() -> None:
    """属性缺失（broker 丢属性 / 手工投递）仍能正确解码。"""
    body = encode_event(EventEnvelope(event_type="sys.user.created", event_id="evt-4"))
    decoded = decode_event(body)
    assert decoded.event_id == "evt-4"
    assert decoded.event_type == "sys.user.created"


def test_decode_rejects_broken_json() -> None:
    """body 非 JSON → 毒消息。"""
    with pytest.raises(EventConsumeError, match="不是合法 JSON"):
        decode_event("{not-json")


def test_decode_rejects_non_object_body() -> None:
    """body 是 JSON 但不是对象 → 毒消息。"""
    with pytest.raises(EventConsumeError, match="不是 JSON 对象"):
        decode_event("[1, 2, 3]")


def test_decode_rejects_missing_event_id() -> None:
    """缺幂等键 → 毒消息（幂等键不可再生，放行会产生重复副作用）。"""
    body = encode_event(EventEnvelope(event_type="sys.user.created"))
    with pytest.raises(EventConsumeError, match="event_id"):
        decode_event(body)


def test_decode_rejects_invalid_event_type() -> None:
    """事件类型缺失或形态非法 → 毒消息。"""
    with pytest.raises(EventConsumeError, match="事件类型非法"):
        decode_event('{"event_id": "evt-5", "event_type": "BadType"}', None)


def test_decode_rejects_non_object_payload() -> None:
    """负载不是 JSON 对象 → 毒消息。"""
    with pytest.raises(EventConsumeError, match="负载不是 JSON 对象"):
        decode_event('{"event_id": "evt-6", "event_type": "sys.user.created", "payload": [1]}', None)


def test_decode_rejects_invalid_occurred_at() -> None:
    """时间格式非法 → 毒消息（不静默按当前时刻兜底，避免错序）。"""
    with pytest.raises(EventConsumeError, match="occurred_at"):
        decode_event('{"event_id": "evt-7", "event_type": "sys.user.created", "occurred_at": "昨天"}', None)


def test_decode_normalizes_timezone_to_naive_utc() -> None:
    """带时区的时间统一折算为 naive UTC（与库表口径一致）。"""
    body = '{"event_id": "evt-8", "event_type": "sys.user.created", "occurred_at": "2026-10-31T10:00:00+08:00"}'
    decoded = decode_event(body)
    assert decoded.occurred_at == datetime(2026, 10, 31, 2, 0, 0, tzinfo=None)


def test_decode_allows_empty_payload() -> None:
    """无负载事件（纯信号）允许，负载为空字典。"""
    decoded = decode_event('{"event_id": "evt-9", "event_type": "sys.user.created"}')
    assert dict(decoded.payload) == {}


def test_encode_is_deterministic() -> None:
    """同信封两次编码字节一致（键排序），便于对账与零漂移比对。"""
    occurred_at = datetime(2026, 10, 31, tzinfo=UTC).replace(tzinfo=None)
    first = EventEnvelope(event_type="sys.user.created", event_id="evt-10", occurred_at=occurred_at)
    second = EventEnvelope(event_type="sys.user.created", event_id="evt-10", occurred_at=occurred_at)
    assert encode_event(first) == encode_event(second)
