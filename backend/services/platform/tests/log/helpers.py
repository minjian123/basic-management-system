"""审计日志用例事件构造器（06_01）。"""

from datetime import datetime

from bms_core.audit.events import LOGIN_LOG_EVENT, OPERATION_LOG_EVENT
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope

NOVEMBER = datetime(2026, 11, 15, 10, 0, 0)
DECEMBER = datetime(2026, 12, 20, 8, 0, 0)


def operation_event(
    event_id: str,
    *,
    tenant_id: str | None = "1001",
    user_id: str = "7",
    module: str = "user",
    action: str = "user:create",
    status: int = 200,
    occurred_at: datetime = NOVEMBER,
    **overrides: object,
) -> EventEnvelope:
    """构造操作日志事件。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "username": "alice",
            "module": module,
            "action": action,
            "method": "POST",
            "path": "/api/v1/users",
            "ip": "10.0.0.1",
            "user_agent": "pytest",
            "cost_time": 5,
            "status": status,
        }
    )
    for key, value in overrides.items():
        payload.set(key, value)
    return EventEnvelope(
        event_type=OPERATION_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}" if tenant_id else "global",
    )


def login_event(
    event_id: str,
    *,
    tenant_id: str = "1001",
    username: str = "alice",
    status: str = "success",
    ip: str = "10.0.0.1",
    occurred_at: datetime = NOVEMBER,
) -> EventEnvelope:
    """构造登录日志事件。"""
    payload = ConcurrentStableDict[str, object](
        {
            "tenant_id": tenant_id,
            "user_id": "1",
            "username": username,
            "ip": ip,
            "user_agent": "pytest",
            "status": status,
        }
    )
    if status != "success":
        payload.set("fail_reason", "bad_credentials")
    return EventEnvelope(
        event_type=LOGIN_LOG_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}",
    )
