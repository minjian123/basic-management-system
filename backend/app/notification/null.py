"""notification 能力域缺省实现（Null Object）：固定返回空集 / 零未读 / None / False，不取数落库。"""

from collections.abc import Sequence

from app.core.capability import BaseNullObject
from app.notification.base import BaseNotificationCenter, Notification
from app.schemas.filters import BaseFilterQuery
from app.schemas.pagination import BasePageQuery, BasePageResponse

__all__ = ["NullNotificationCenter"]


class NullNotificationCenter(BaseNotificationCenter, BaseNullObject):
    """占位通知中心：列表空、详情 None、未读 0、已读返回 0、删除失败（不取数落库、不推送）。"""

    async def list(self, filter: BaseFilterQuery, page: BasePageQuery) -> BasePageResponse[Notification]:
        """列当前用户通知（占位恒空）。

        Args:
            filter: 筛选契约（占位忽略）。
            page: 分页契约（占位回显页码 / 条数）。

        Returns:
            BasePageResponse[Notification]: 空分页。
        """
        return BasePageResponse[Notification](list=[], total=0, page=page.page, size=page.size)

    async def detail(self, notification_id: int, *, mark_read: bool = True) -> Notification | None:
        """取通知详情（占位恒未命中）。

        Args:
            notification_id: 通知 ID（占位忽略）。
            mark_read: 命中是否标记已读（占位忽略）。

        Returns:
            Notification | None: None。
        """
        return None

    async def unread_count(self) -> int:
        """当前未读总数（占位恒 0）。

        Returns:
            int: 0。
        """
        return 0

    async def mark_read(self, ids: Sequence[int]) -> int:
        """按 id 批量标记已读（占位恒无变更）。

        Args:
            ids: 通知 ID 序列（占位忽略）。

        Returns:
            int: 操作后未读总数（0）。
        """
        return 0

    async def mark_all_read(self) -> int:
        """全部标记已读（占位恒无变更）。

        Returns:
            int: 操作后未读总数（0）。
        """
        return 0

    async def delete(self, notification_id: int) -> bool:
        """删除单条通知（占位恒无既有通知）。

        Args:
            notification_id: 通知 ID（占位忽略）。

        Returns:
            bool: False。
        """
        return False
