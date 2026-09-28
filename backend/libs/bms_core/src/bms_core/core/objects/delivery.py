"""值对象体系 · 投递结果链层：通知 / Webhook 投递结果。

**链结构（按公共段成层，本次 1 层）**：

- `BaseDeliveryResultContract`（公共段 `delivered`）——站内 / 外部投递结果共用送达位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseDeliveryResultContract"]


@dataclass(frozen=True)
class BaseDeliveryResultContract(BaseValueObject):
    """投递结果契约（角色链层）：**送达位**统一读面。

    公共段：`delivered`（是否送达）——通知发送（`SendResult`）与 Webhook 投递（`WebhookResult`）
    共用；调用方据同一字段判定成败，无需区分渠道。渠道自有字段（消息标识 / 状态码 / 尝试次数）
    由成员声明，不入公共段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("delivered",)
