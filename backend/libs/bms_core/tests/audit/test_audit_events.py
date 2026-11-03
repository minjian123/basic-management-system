"""审计事件构造与脱敏护栏（06_01）：载荷字段 / 聚合键 / 时间规范化 / 敏感值。"""

from datetime import UTC, datetime, timedelta, timezone
from typing import cast

import pytest

from bms_core.audit.events import (
    GLOBAL_AUDIT_TENANT,
    LOGIN_LOG_EVENT,
    OPERATION_LOG_EVENT,
    audit_aggregate_key,
    build_login_event,
    build_operation_event,
    month_of,
    normalize_occurred_at,
)
from bms_core.core.logging import mask_sensitive

pytestmark = pytest.mark.kiwi_id(2407)


def test_operation_event_builds_payload_and_envelope() -> None:
    """操作事件：必填字段入载荷、可选空字段省略、租户位与聚合键一致。"""
    event = build_operation_event(
        tenant_id="1001",
        user_id=7,
        username=None,
        module="user",
        action="user:create",
        method="POST",
        path="/api/v1/users",
        query=None,
        params='{"password":"***"}',
        ip="10.0.0.1",
        user_agent="pytest",
        cost_time=12,
        status=200,
        error_msg=None,
        occurred_at=datetime(2026, 11, 3, 1, 2, 3),
    )
    assert event.event_type == OPERATION_LOG_EVENT
    assert event.tenant_id == "1001"
    assert event.aggregate_key == "tenant:1001"
    assert event.payload["user_id"] == "7"
    assert event.payload["status"] == 200
    assert event.occurred_at == datetime(2026, 11, 3, 1, 2, 3)
    assert "occurred_at" not in event.payload
    assert "trace_id" not in event.payload
    assert "username" not in event.payload
    assert "error_msg" not in event.payload


def test_login_event_and_global_aggregate() -> None:
    """登录事件：失败原因入载荷；无租户聚合键为 global。"""
    event = build_login_event(
        tenant_id=None,
        user_id=None,
        username="alice",
        ip=None,
        user_agent=None,
        status="failed",
        fail_reason="bad_credentials",
    )
    assert event.event_type == LOGIN_LOG_EVENT
    assert event.aggregate_key == GLOBAL_AUDIT_TENANT
    assert audit_aggregate_key(None) == GLOBAL_AUDIT_TENANT
    assert event.payload["fail_reason"] == "bad_credentials"
    assert "ip" not in event.payload


def test_time_normalization_and_month() -> None:
    """时间：带时区转 UTC naive；月键取 UTC 月份。"""
    aware = datetime(2026, 11, 30, 23, 30, tzinfo=timezone(timedelta(hours=8)))
    normalized = normalize_occurred_at(aware)
    assert normalized == datetime(2026, 11, 30, 15, 30)
    assert month_of(normalized) == "202611"
    assert normalize_occurred_at(datetime(2026, 1, 2, 3, 4, 5)).tzinfo is None
    assert normalize_occurred_at().tzinfo is None


def test_mask_sensitive_reuses_log_lists_and_is_pure() -> None:
    """脱敏：敏感键 / 后缀 / PII 置 ***；嵌套结构递归；不改入参。"""
    payload = {
        "username": "alice",
        "password": "secret",
        "nested": {"access_token": "t", "phone": "13800000000", "ok": 1},
        "items": [{"client_secret": "s"}, {"note": "keep"}],
        "db_url": "mysql+pymysql://root:pass@localhost:3306/db",
        "x_password": "hide",
    }
    masked = cast("dict[str, object]", mask_sensitive(payload))
    nested = cast("dict[str, object]", masked["nested"])
    items = cast("list[dict[str, object]]", masked["items"])
    assert masked["username"] == "alice"
    assert masked["password"] == "***"
    assert nested["access_token"] == "***"
    assert nested["phone"] == "***"
    assert nested["ok"] == 1
    assert items[0]["client_secret"] == "***"
    assert items[1]["note"] == "keep"
    assert masked["db_url"] == "mysql+pymysql://root:***@localhost:3306/db"
    assert masked["x_password"] == "***"
    assert payload["password"] == "secret"  # 原对象不被修改
    assert mask_sensitive("plain") == "plain"
    assert mask_sensitive(3) == 3
    deep = mask_sensitive({"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}})
    assert isinstance(deep, dict)
    assert month_of(datetime(2026, 12, 1, tzinfo=UTC)) == "202612"
