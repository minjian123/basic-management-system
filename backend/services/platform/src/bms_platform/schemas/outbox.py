"""schemas 层死信看板契约：事件死信记录响应。"""

from datetime import datetime
from typing import Any

from bms_core.schemas.base import BaseSchema


class DeadLetterResponse(BaseSchema):
    """死信记录响应（与 `sys_event_dead_letter` 对齐）。"""

    id: int
    source: str
    event_id: str
    event_type: str
    consumer: str | None
    aggregate_key: str | None
    tenant_id: str | None
    payload: dict[str, Any]
    error_msg: str
    retry_count: int
    status: str
    occurred_at: datetime
