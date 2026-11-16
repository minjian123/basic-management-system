"""审计合规用例：事件构造器（06_02）。"""

from datetime import datetime

from bms_core.audit.events import DATA_CHANGED_EVENT
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.events.base import EventEnvelope

NOVEMBER = datetime(2026, 11, 15, 10, 0, 0)
DECEMBER = datetime(2026, 12, 20, 8, 0, 0)


def data_event(
    event_id: str,
    *,
    tenant_id: str | None = "1001",
    table: str = "sys_role",
    model_id: str | None = "42",
    field: str = "name",
    old_value: str | None = "旧名",
    new_value: str | None = "新名",
    operator_id: str | None = "7",
    domain_key: str | None = "role",
    occurred_at: datetime = NOVEMBER,
    **overrides: object,
) -> EventEnvelope:
    """构造字段级变更审计事件（默认值与 `build_data_changed_event` 同形）。

    Args:
        event_id: 幂等键。
        tenant_id: 租户主键（None 为全局链）。
        table: 被审计表名。
        model_id: 被审计记录主键。
        field: 变更字段名。
        old_value: 变更前值。
        new_value: 变更后值。
        operator_id: 操作人主键。
        domain_key: 业务域。
        occurred_at: 事件时间。
        **overrides: 覆盖 / 追加载荷字段。

    Returns:
        EventEnvelope: 事件信封。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict({"table": table, "field": field})
    if tenant_id is not None:
        payload.set("tenant_id", tenant_id)
    if model_id is not None:
        payload.set("model_id", model_id)
    if operator_id is not None:
        payload.set("operator_id", operator_id)
    if domain_key is not None:
        payload.set("domain_key", domain_key)
    if old_value is not None:
        payload.set("old_value", old_value)
    if new_value is not None:
        payload.set("new_value", new_value)
    for key, value in overrides.items():
        payload.set(key, value)
    return EventEnvelope(
        event_type=DATA_CHANGED_EVENT,
        payload=payload,
        tenant_id=tenant_id,
        occurred_at=occurred_at,
        event_id=event_id,
        aggregate_key=f"tenant:{tenant_id}" if tenant_id else "global",
    )
