"""工作台角标响应模型（`/dashboard/badges`）。"""

from __future__ import annotations

from pydantic import Field

from bms_core.schemas.base import BaseSchema

__all__ = ["DashboardBadgeCount", "DashboardBadges"]


class DashboardBadgeCount(BaseSchema):
    """单个角标（计数 + 可用性；不可用时前端隐藏角标）。"""

    count: int = Field(ge=0, description="计数（不可用时为 0）")
    available: bool = Field(description="数据来源是否可用")
    reason: str | None = Field(default=None, max_length=64, description="不可用原因")


class DashboardBadges(BaseSchema):
    """角标聚合响应（顶栏 / 侧边栏统一出口）。"""

    todo: DashboardBadgeCount = Field(description="待办角标（工作流落地前不可用）")
    notification: DashboardBadgeCount = Field(description="未读通知角标（通知服务为唯一口径）")
