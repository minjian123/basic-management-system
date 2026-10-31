"""事件通道编码：topic 派生与「信封 ↔ 消息体 / 消息属性」编解码（纯函数，无 IO）。

- **topic 派生**：`bms.{事件域}.{对象}`——取事件名前两段。同对象的多个动作落同一 topic
  （`wf.task` 承载 created / completed / rejected），topic 数量不随动作数膨胀；订阅仍按
  `event_type` 精确匹配（组内声明），topic 只承担通道与分区职责。
- **消息体**：完整信封 JSON，确定性输出（键排序、非 ASCII 直出），便于对账与排障。
- **消息属性**：幂等键 / 类型 / 版本 / 租户 / 聚合键 / 链路——broker 侧可按幂等键检索，
  消费端优先读属性、缺失回落 body（属性丢失仍可正确解码）。
- **毒消息判定**（抛 `EventConsumeError`，消费组不重试、直接死信）：body 非法 JSON、
  `event_type` 缺失或不符 `EVENT_TYPE_RE`、`payload` 非对象、`event_id` 缺失（幂等键不可再生）。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import EventConsumeError
from bms_core.events.base import DEFAULT_EVENT_VERSION, EventEnvelope
from bms_core.events.contracts import EVENT_TYPE_RE

__all__ = [
    "ATTR_AGGREGATE_KEY",
    "ATTR_EVENT_ID",
    "ATTR_EVENT_TYPE",
    "ATTR_EVENT_VERSION",
    "ATTR_OCCURRED_AT",
    "ATTR_TENANT_ID",
    "ATTR_TRACEPARENT",
    "ATTR_TRACE_ID",
    "TOPIC_MAX_SEGMENTS",
    "TOPIC_PREFIX",
    "decode_event",
    "encode_event",
    "event_attributes",
    "topic_for",
]

TOPIC_PREFIX = "bms"
"""topic 前缀（与《命名规范》「RocketMQ topic」同口径）。"""

TOPIC_MAX_SEGMENTS = 2
"""topic 取事件名前几段（域 + 对象）。"""

ATTR_EVENT_ID = "event_id"
"""消息属性：幂等键。"""

ATTR_EVENT_TYPE = "event_type"
"""消息属性：事件类型。"""

ATTR_EVENT_VERSION = "event_version"
"""消息属性：事件契约版本。"""

ATTR_TENANT_ID = "tenant_id"
"""消息属性：租户主键（无租户事件缺省）。"""

ATTR_AGGREGATE_KEY = "aggregate_key"
"""消息属性：聚合 / 分区键。"""

ATTR_OCCURRED_AT = "occurred_at"
"""消息属性：事件发生时间（ISO8601，naive UTC）。"""

ATTR_TRACE_ID = "trace_id"
"""消息属性：链路 id（无 OTel 时透传）。"""

ATTR_TRACEPARENT = "traceparent"
"""消息属性：W3C 链路上下文（有 OTel 时生成，消费端据此续接 span）。"""

_BODY_EVENT_ID = "event_id"
_BODY_PAYLOAD = "payload"


def topic_for(event_type: str) -> str:
    """按事件类型派生 topic（`bms.{事件域}.{对象}`）。

    Args:
        event_type: 事件类型（`{域}.{对象}.{动作}`，至少两段）。

    Returns:
        str: topic 名（如 `sys.user.created` → `bms.sys.user`）。

    Raises:
        EventConsumeError: 事件类型不合规（段数不足 / 形态非法）。
    """
    if not EVENT_TYPE_RE.match(event_type):
        raise EventConsumeError(f"事件类型非法，无法派生 topic：{event_type!r}")
    parts = event_type.split(".")
    return ".".join((TOPIC_PREFIX, *parts[:TOPIC_MAX_SEGMENTS]))


def encode_event(event: EventEnvelope) -> bytes:
    """把事件信封编码为消息体（确定性 JSON）。

    Args:
        event: 事件信封（`event_id` / `occurred_at` 由发件箱补齐，此处缺省按当前时刻兜底）。

    Returns:
        bytes: UTF-8 JSON 消息体。
    """
    occurred_at = event.occurred_at or datetime.now(UTC).replace(tzinfo=None)
    body: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_version": event.event_version or DEFAULT_EVENT_VERSION,
            "tenant_id": event.tenant_id,
            "trace_id": event.trace_id,
            "aggregate_key": event.aggregate_key,
            "occurred_at": occurred_at.isoformat(),
            _BODY_PAYLOAD: dict(event.payload),
        }
    )
    return json.dumps(dict(body), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")


def event_attributes(event: EventEnvelope, *, traceparent: str | None = None) -> ConcurrentStableDict[str, str]:
    """构造消息属性（空值不落属性，避免消费端把空串当值）。

    Args:
        event: 事件信封。
        traceparent: W3C 链路上下文（有 OTel 时传入）。

    Returns:
        ConcurrentStableDict[str, str]: 消息属性（仅含非空项）。
    """
    occurred_at = event.occurred_at or datetime.now(UTC).replace(tzinfo=None)
    candidates: ConcurrentStableDict[str, str | None] = ConcurrentStableDict(
        {
            ATTR_EVENT_ID: event.event_id,
            ATTR_EVENT_TYPE: event.event_type,
            ATTR_EVENT_VERSION: event.event_version or DEFAULT_EVENT_VERSION,
            ATTR_TENANT_ID: event.tenant_id,
            ATTR_AGGREGATE_KEY: event.aggregate_key,
            ATTR_TRACE_ID: event.trace_id,
            ATTR_TRACEPARENT: traceparent,
            ATTR_OCCURRED_AT: occurred_at.isoformat(),
        }
    )
    return ConcurrentStableDict({key: value for key, value in candidates.items() if value})


def decode_event(body: bytes | str, attributes: ConcurrentStableDict[str, str] | None = None) -> EventEnvelope:
    """把消息体与属性解码为事件信封（属性优先、缺失回落 body）。

    Args:
        body: 消息体（UTF-8 JSON）。
        attributes: 消息属性（可为空；缺省空表）。

    Returns:
        EventEnvelope: 事件信封。

    Raises:
        EventConsumeError: 毒消息（body 非法 / 缺 `event_id` / 事件类型非法 / payload 非对象）。
    """
    parsed = _parse_body(body)
    attrs = attributes or {}
    event_type = attrs.get(ATTR_EVENT_TYPE) or _as_str(parsed.get("event_type"))
    if not event_type or not EVENT_TYPE_RE.match(event_type):
        raise EventConsumeError(f"消息事件类型非法：{event_type!r}")
    event_id = attrs.get(ATTR_EVENT_ID) or _as_str(parsed.get(_BODY_EVENT_ID))
    if not event_id:
        raise EventConsumeError(f"消息缺幂等键 event_id：{event_type}")
    payload = _parse_payload(parsed.get(_BODY_PAYLOAD), event_type=event_type)
    return EventEnvelope(
        event_type=event_type,
        payload=payload,
        tenant_id=attrs.get(ATTR_TENANT_ID) or _as_str(parsed.get("tenant_id")),
        trace_id=attrs.get(ATTR_TRACE_ID) or _as_str(parsed.get("trace_id")),
        event_id=event_id,
        occurred_at=_parse_occurred_at(attrs.get(ATTR_OCCURRED_AT) or _as_str(parsed.get("occurred_at"))),
        aggregate_key=attrs.get(ATTR_AGGREGATE_KEY) or _as_str(parsed.get("aggregate_key")),
        event_version=attrs.get(ATTR_EVENT_VERSION) or _as_str(parsed.get("event_version")),
    )


def _parse_body(body: bytes | str) -> ConcurrentStableDict[str, object]:
    """解析消息体 JSON。

    Args:
        body: 消息体。

    Returns:
        ConcurrentStableDict[str, object]: 解析结果。

    Raises:
        EventConsumeError: 非法 JSON 或非对象。
    """
    raw = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise EventConsumeError(f"消息体不是合法 JSON：{raw[:120]!r}") from exc
    if not isinstance(loaded, dict):
        raise EventConsumeError(f"消息体不是 JSON 对象：{type(loaded).__name__}")
    return ConcurrentStableDict(cast("dict[str, object]", loaded))


def _parse_payload(raw: object, *, event_type: str) -> ConcurrentStableDict[str, object]:
    """解析事件负载（缺省空载荷；非对象视为毒消息）。

    Args:
        raw: body 中的负载段。
        event_type: 事件类型（错误信息用）。

    Returns:
        ConcurrentStableDict[str, object]: 事件负载。

    Raises:
        EventConsumeError: 负载不是 JSON 对象。
    """
    if raw is None:
        return ConcurrentStableDict()
    if not isinstance(raw, dict):
        raise EventConsumeError(f"事件负载不是 JSON 对象：{event_type} → {type(raw).__name__}")
    return ConcurrentStableDict(cast("dict[str, object]", raw))


def _parse_occurred_at(raw: str | None) -> datetime | None:
    """解析发生时间（ISO8601，统一为 naive UTC）。

    Args:
        raw: 时间字符串。

    Returns:
        datetime | None: 解析结果；缺失或非法返回 None（由消费侧按当前时刻兜底）。

    Raises:
        EventConsumeError: 时间格式非法（毒消息，避免静默错序）。
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EventConsumeError(f"occurred_at 非法：{raw!r}") from exc
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _as_str(value: object) -> str | None:
    """把 body 中的标量转为字符串（None 与空串归一为 None）。

    Args:
        value: body 字段值。

    Returns:
        str | None: 字符串值。
    """
    if value is None:
        return None
    text = str(value)
    return text or None
