"""通知中心读面服务：列表 / 详情（查看即已读）/ 未读数 / 已读 / 删除。

用户维度固定为 `current_user_id`；跨用户详情 / 删除按错误码拒绝，批量已读静默忽略他人 id。
事务由调用方（通知中心适配器 / 路由工作单元）负责，本层只 `flush`。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import get_current_user_id
from bms_core.core.exceptions import (
    NotificationBatchInvalidError,
    NotificationDeleteForbiddenError,
    NotificationForbiddenError,
    NotificationNotFoundError,
    ParamError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.notification.base import Notification
from bms_core.notification.types import NOTIFICATION_TYPES
from bms_core.schemas.filters import BaseFilterQuery, FilterSpec
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_notification.domains.notification.models.notification import SysNotification
from bms_notification.domains.notification.repositories.notification import NotificationRepository

__all__ = ["MARK_READ_LIMIT", "NotificationService"]

MARK_READ_LIMIT = 500
"""批量已读单次上限（概要 70003 / 70103 语义）。"""


class NotificationService(BaseFrameworkObject):
    """通知中心读面服务（当前用户维度）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._session = session
        self._repository = NotificationRepository(session)

    async def list(self, filter: BaseFilterQuery, page: BasePageQuery) -> BasePageResponse[Notification]:
        """列当前用户通知。

        Args:
            filter: 筛选契约（`keyword` + `filters`）。
            page: 分页契约。

        Returns:
            BasePageResponse[Notification]: 分页通知。

        Raises:
            ParamError: 筛选字段 / 操作符不受支持（`10001`）。
        """
        user_id = self._require_user()
        notification_type, is_read = self._parse_filters(filter.filters)
        rows, total = await self._repository.page_for_user(
            user_id,
            page=page.page,
            size=page.size,
            keyword=filter.keyword,
            notification_type=notification_type,
            is_read=is_read,
        )
        return BasePageResponse[Notification](
            list=ConcurrentStableList(_to_contract(row) for row in rows),
            total=total,
            page=page.page,
            size=page.size,
        )

    async def detail(self, notification_id: int, *, mark_read: bool = True) -> Notification:
        """取通知详情（查看即已读）。

        Args:
            notification_id: 通知主键。
            mark_read: 命中是否标记已读。

        Returns:
            Notification: 通知对象。

        Raises:
            NotificationNotFoundError: 通知不存在（`70101`）。
            NotificationForbiddenError: 非本人通知（`70102`）。
        """
        user_id = self._require_user()
        row = await self._repository.get_any(notification_id)
        if row is None:
            raise NotificationNotFoundError(f"通知不存在：{notification_id}")
        if row.user_id != user_id:
            raise NotificationForbiddenError("无权读取他人通知")
        if mark_read and not row.is_read:
            row.is_read = True
            await self._session.flush()
        return _to_contract(row)

    async def unread_count(self) -> int:
        """当前用户未读总数。

        Returns:
            int: 未读数。
        """
        return await self._repository.unread_count(self._require_user())

    async def unread_count_for(self, user_id: int) -> int:
        """按显式用户取未读数（服务间内部面用；不经登录态上下文）。

        Args:
            user_id: 用户主键（由调用方服务身份担保，入站已校验）。

        Returns:
            int: 未读数。
        """
        return await self._repository.unread_count(user_id)

    async def mark_read(self, ids: ConcurrentStableList[int]) -> int:
        """按 id 批量标记已读（幂等）。

        Args:
            ids: 通知主键清单。

        Returns:
            int: 操作后的未读总数。

        Raises:
            NotificationBatchInvalidError: id 为空或超过上限（`70103`）。
        """
        if not ids:
            raise NotificationBatchInvalidError("批量已读 id 列表不得为空")
        if len(ids) > MARK_READ_LIMIT:
            raise NotificationBatchInvalidError(f"批量已读单次不得超过 {MARK_READ_LIMIT} 条")
        user_id = self._require_user()
        await self._repository.mark_read(user_id, ids)
        return await self._repository.unread_count(user_id)

    async def mark_all_read(self) -> int:
        """全部标记已读。

        Returns:
            int: 操作后的未读总数（恒 0）。
        """
        user_id = self._require_user()
        await self._repository.mark_all_read(user_id)
        return 0

    async def delete(self, notification_id: int) -> bool:
        """删除单条通知（软删除，仅本人）。

        Args:
            notification_id: 通知主键。

        Returns:
            bool: 是否删除到既有通知。

        Raises:
            NotificationNotFoundError: 通知不存在（`70101`）。
            NotificationDeleteForbiddenError: 非本人通知（`70106`）。
        """
        user_id = self._require_user()
        row = await self._repository.get_any(notification_id)
        if row is None:
            raise NotificationNotFoundError(f"通知不存在：{notification_id}")
        if row.user_id != user_id:
            raise NotificationDeleteForbiddenError("无权删除他人通知")
        row.soft_delete()
        await self._session.flush()
        return True

    @staticmethod
    def _require_user() -> int:
        """取当前用户主键。

        Returns:
            int: 用户主键。

        Raises:
            ParamError: 无登录用户上下文（`10001`）。
        """
        user_id = get_current_user_id()
        if user_id is None:
            raise ParamError("缺少登录用户上下文")
        return user_id

    @staticmethod
    def _parse_filters(filters: ConcurrentStableList[FilterSpec]) -> tuple[str | None, bool | None]:
        """解析通用筛选条件中的类型 / 已读。

        Args:
            filters: 筛选条件。

        Returns:
            tuple[str | None, bool | None]: （类型, 已读）。

        Raises:
            ParamError: 字段 / 操作符 / 类型值不受支持（`10001`）。
        """
        notification_type: str | None = None
        is_read: bool | None = None
        for spec in filters:
            if spec.operator != "eq":
                raise ParamError(f"通知列表不支持筛选操作符：{spec.operator}")
            if spec.field == "type":
                value = str(spec.value or "")
                if value not in NOTIFICATION_TYPES:
                    raise ParamError(f"通知类型非法：{value}")
                notification_type = value
            elif spec.field == "is_read":
                value = spec.value
                if isinstance(value, bool):
                    is_read = value
                elif isinstance(value, int) and value in (0, 1):
                    is_read = bool(value)
                elif isinstance(value, str) and value.lower() in ("0", "1", "true", "false"):
                    is_read = value.lower() in ("1", "true")
                else:
                    raise ParamError(f"已读筛选值非法：{value!r}")
            else:
                raise ParamError(f"通知列表不支持筛选字段：{spec.field}")
        return notification_type, is_read


def _to_contract(row: SysNotification) -> Notification:
    """ORM 行 → 数据契约。

    Args:
        row: 通知行。

    Returns:
        Notification: 通知对象。
    """
    return Notification(
        id=int(row.id),
        user_id=int(row.user_id),
        title=row.title,
        content=row.content,
        type=row.type,
        biz_type=row.biz_type,
        biz_id=row.biz_id,
        is_read=bool(row.is_read),
        created_at=row.created_at,
    )
