"""通知中心请求 / 响应契约：批量已读请求与未读计数响应（占位路由用）。"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema

__all__ = ["NotificationReadRequest", "UnreadCountResponse"]


class NotificationReadRequest(BaseSchema):
    """批量已读请求：待标记已读的通知 ID 列表。"""

    ids: Annotated[ConcurrentStableList[int], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="通知 ID 列表"
    )


class UnreadCountResponse(BaseSchema):
    """未读计数响应（`unread_count` 及已读接口返回的操作后未读总数）。"""

    count: int = Field(default=0, ge=0, description="未读通知数")
