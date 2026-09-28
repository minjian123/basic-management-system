"""值对象体系 · 事件记录链层：发件箱与死信记录。

**链结构（按公共段成层，本次 1 层）**：

- `BaseEventRecordContract`（公共段 `event_id` + `event_type` + `tenant_id` + `payload` + `status`）
  ——发件箱记录与死信记录共用事件标识与载荷。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseEventRecordContract"]


@dataclass(frozen=True)
class BaseEventRecordContract(BaseValueObject):
    """事件记录契约（角色链层）：事件落库记录的**统一读面**。

    公共段：`event_id`（事件标识）+ `event_type`（事件类型）+ `tenant_id`（租户）+ `payload`（载荷）+
    `status`（投递 / 处理状态）——发件箱记录与死信记录共用；重投、对账、死信追查按同一组字段定位。
    各记录自有字段（重试次数 / 错误信息 / 聚合键 / 时间位）由成员声明，不入公共段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("event_id", "event_type", "tenant_id", "payload", "status")
