"""首页工作台域只读 DTO（跨域出口与端口返回值用；不可变数据类，落 `BaseValueObject`）。"""

from dataclasses import dataclass

from bms_core.core.objects import BaseValueObject

__all__ = ["BadgeCountView"]


@dataclass(frozen=True)
class BadgeCountView(BaseValueObject):
    """角标计数视图（`count` + 可用性；不可用时由前端隐藏角标而非报错）。"""

    count: int = 0
    """计数（不可用时为 0）。"""
    available: bool = True
    """数据来源是否可用。"""
    reason: str | None = None
    """不可用原因（`workflow_unavailable` / `notification_unavailable` 等）。"""
