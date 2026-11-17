"""通知域仓储：按用户分页 / 未读数 / 批量已读 / 软删除（`sys_notification`）。

软删除与作用域条件由基座 `_select()` 统一施加，本层不重复写 `deleted_at IS NULL`。
"""

from __future__ import annotations

from sqlalchemy import func, select, update

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_notification.domains.notification.models.notification import SysNotification

__all__ = ["NotificationRepository"]


class NotificationRepository(BaseDbRepository[SysNotification]):
    """站内信仓储（个人维度）。"""

    model = SysNotification
    sortable_fields = ConcurrentStableSet({"created_at", "id"})

    async def page_for_user(
        self,
        user_id: int,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        notification_type: str | None = None,
        is_read: bool | None = None,
    ) -> tuple[ConcurrentStableList[SysNotification], int]:
        """按用户筛选分页（创建时间倒序）。

        Args:
            user_id: 当前用户主键。
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 标题关键字（模糊匹配）。
            notification_type: 通知类型。
            is_read: 已读状态。

        Returns:
            tuple[ConcurrentStableList[SysNotification], int]: （当页记录, 总数）。
        """
        statement = self._select().where(SysNotification.user_id == user_id)
        if keyword:
            statement = statement.where(SysNotification.title.contains(keyword, autoescape=True))
        if notification_type:
            statement = statement.where(SysNotification.type == notification_type)
        if is_read is not None:
            statement = statement.where(SysNotification.is_read.is_(is_read))
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(SysNotification.created_at.desc(), SysNotification.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def get_any(self, notification_id: int) -> SysNotification | None:
        """按主键取记录（不限定用户，供越权判定）。

        Args:
            notification_id: 通知主键。

        Returns:
            SysNotification | None: 记录；不存在 None。
        """
        statement = self._select().where(SysNotification.id == notification_id)
        return (await self._session.execute(statement)).scalars().first()

    async def unread_count(self, user_id: int) -> int:
        """统计用户未读数。

        Args:
            user_id: 用户主键。

        Returns:
            int: 未读数。
        """
        statement = (
            select(func.count())
            .select_from(SysNotification)
            .where(
                SysNotification.user_id == user_id,
                SysNotification.is_read.is_(False),
                SysNotification.deleted_at.is_(None),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def mark_read(self, user_id: int, ids: ConcurrentStableList[int]) -> None:
        """把本人指定未读通知标记为已读（他人 id 自动忽略）。

        Args:
            user_id: 用户主键。
            ids: 通知主键清单。
        """
        if not ids:
            return
        await self._session.execute(
            update(SysNotification)
            .where(
                SysNotification.user_id == user_id,
                SysNotification.id.in_(list(ids)),
                SysNotification.is_read.is_(False),
                SysNotification.deleted_at.is_(None),
            )
            .values(is_read=True)
        )
        await self._session.flush()

    async def mark_all_read(self, user_id: int) -> None:
        """把本人全部未读通知标记为已读。

        Args:
            user_id: 用户主键。
        """
        await self._session.execute(
            update(SysNotification)
            .where(
                SysNotification.user_id == user_id,
                SysNotification.is_read.is_(False),
                SysNotification.deleted_at.is_(None),
            )
            .values(is_read=True)
        )
        await self._session.flush()
