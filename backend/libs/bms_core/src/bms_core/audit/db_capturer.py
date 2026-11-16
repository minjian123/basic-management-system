"""审计捕获真实实现 `DbAuditCapturer`（06_02）：字段级变更 → `sys.data.changed` 事件。

两条通道分工：

- **写库路径**（绝大多数）：由 `audit/field_capture.py` 的 ORM 会话事件在业务事务内直接入发件箱——
  业务代码零侵入，`capture()` 不参与；
- **显式留痕**（三权分立拒绝、账号锁定处置等**不写库**的判定场景）：端点 / 服务调 `capture()`，
  本实现把变更转成事件投入请求级暂存（`audit/staging.py`），由审计中间件在响应收尾统一发射；
  同 `(表, 主键, 字段)` 与 ORM 通道去重（`reserve_capture_key`），不会写两条。

`changes` 为空时**不产生任何记录**（这类场景「调了哪个接口」由操作日志覆盖），仅返回占位信封以维持
既有调用面签名。
"""

from __future__ import annotations

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.audit.events import build_data_changed_event
from bms_core.audit.field_capture import reserve_capture_key
from bms_core.audit.staging import stage_event
from bms_core.audit.tables import is_audited_table
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import get_current_user_id
from bms_core.db.tenant import current_tenant_id_str
from bms_core.events.base import EventEnvelope

__all__ = ["TOUCH_FIELD", "DbAuditCapturer"]

TOUCH_FIELD = "*"
"""占位信封的字段名（`changes` 为空时使用；该信封**不入暂存、不落库**）。"""


class DbAuditCapturer(AuditCapturer):
    """字段级变更审计捕获实现（白名单判定 + 显式留痕暂存）。"""

    plugin_name: str = "db"

    def is_audited(self, table: str) -> bool:
        """判断表是否纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: 纳入为 True。
        """
        return is_audited_table(table)

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """把显式留痕的字段变更转成事件并暂存（响应收尾统一发射）。

        Args:
            table: 逻辑表名。
            model_id: 记录主键（无实体记录可用 `0`）。
            changes: 字段变更列表（空 = 不产生记录）。
            actor: 操作者 ID（None 取请求上下文）。

        Returns:
            EventEnvelope: 首个变更的事件信封；无变更时返回不入库的占位信封。
        """
        tenant_id = current_tenant_id_str()
        operator_id = actor if actor is not None else get_current_user_id()
        events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()
        for change in changes:
            if not reserve_capture_key(table, model_id, change.field):
                continue
            events.add(
                build_data_changed_event(
                    tenant_id=tenant_id,
                    table=table,
                    model_id=model_id,
                    field=change.field,
                    old_value=change.old,
                    new_value=change.new,
                    operator_id=operator_id,
                )
            )
        for event in events:
            stage_event(event)
        if events:
            return events[0]
        return build_data_changed_event(
            tenant_id=tenant_id,
            table=table,
            model_id=model_id,
            field=TOUCH_FIELD,
            operator_id=operator_id,
        )
