"""公告域仓储：管理 / 公开分页、已读回执、统计与过期扫描（`sys_notice` / `sys_notice_read`）。

软删除与作用域条件由基座 `_select()` 统一施加，本层不重复写 `deleted_at IS NULL`。
公告可见性（发布中 + 时间窗口）在仓储以 SQL 条件下推，避免服务层二次过滤分页总数。
"""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql.elements import ColumnElement

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_notification.domains.notification.models.notice import SysNotice, SysNoticeRead
from bms_notification.domains.notification.notice_constants import (
    NOTICE_STATUS_OFFLINE,
    NOTICE_STATUS_PUBLISHED,
)

__all__ = ["NoticeRepository"]


class NoticeRepository(BaseDbRepository[SysNotice]):
    """公告仓储（管理 / 公开两个读面 + 回执 + 过期扫描）。"""

    model = SysNotice
    sortable_fields = ConcurrentStableSet({"created_at", "id", "publish_at", "updated_at", "is_top"})

    async def page_manage(
        self,
        *,
        page: int,
        size: int,
        now: datetime,
        keyword: str | None = None,
        status: str | None = None,
        notice_type: str | None = None,
        visible_only: bool = False,
    ) -> tuple[ConcurrentStableList[SysNotice], int]:
        """管理列表分页（可按状态 / 类型 / 关键字筛选）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            now: 当前 UTC 时间（可见性判定）。
            keyword: 标题关键字（模糊匹配）。
            status: 状态（`draft` / `published` / `offline`）。
            notice_type: 公告类型（选项集 value）。
            visible_only: 仅返回发布中且未过期（普通用户无 `notice:update` 时强制）。

        Returns:
            tuple[ConcurrentStableList[SysNotice], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if visible_only:
            statement = self._visible(statement, now)
        elif status:
            statement = statement.where(SysNotice.status == status)
        if notice_type:
            statement = statement.where(SysNotice.type == notice_type)
        if keyword:
            statement = statement.where(SysNotice.title.contains(keyword, autoescape=True))
        return await self._page(statement, page=page, size=size)

    async def page_published(
        self, *, page: int, size: int, now: datetime
    ) -> tuple[ConcurrentStableList[SysNotice], int]:
        """全员发布中列表分页（置顶优先）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            now: 当前 UTC 时间（可见性判定）。

        Returns:
            tuple[ConcurrentStableList[SysNotice], int]: （当页记录, 总数）。
        """
        statement = self._visible(self._select(), now)
        return await self._page(statement, page=page, size=size)

    async def get_any(self, notice_id: int) -> SysNotice | None:
        """按主键取公告（含草稿 / 下线，供可见性判定）。

        Args:
            notice_id: 公告主键。

        Returns:
            SysNotice | None: 公告行；不存在 None。
        """
        statement = self._select().where(SysNotice.id == notice_id)
        return (await self._session.execute(statement)).scalars().first()

    async def read_ids(self, user_id: int, notice_ids: ConcurrentStableList[int]) -> ConcurrentStableSet[int]:
        """取当前用户在给定公告集合中的已读公告主键。

        Args:
            user_id: 当前用户主键。
            notice_ids: 公告主键清单（空直接返回空集）。

        Returns:
            ConcurrentStableSet[int]: 已读公告主键集合。
        """
        if not notice_ids:
            return ConcurrentStableSet()
        statement = (
            select(SysNoticeRead.notice_id)
            .where(
                SysNoticeRead.user_id == user_id,
                SysNoticeRead.notice_id.in_(list(notice_ids)),
                SysNoticeRead.deleted_at.is_(None),
            )
            .order_by(SysNoticeRead.notice_id)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableSet(int(row) for row in rows)

    async def get_receipt(self, notice_id: int, user_id: int) -> SysNoticeRead | None:
        """取某公告某用户的活回执。

        Args:
            notice_id: 公告主键。
            user_id: 用户主键。

        Returns:
            SysNoticeRead | None: 回执行；不存在 None。
        """
        statement = (
            select(SysNoticeRead)
            .where(
                SysNoticeRead.notice_id == notice_id,
                SysNoticeRead.user_id == user_id,
                SysNoticeRead.deleted_at.is_(None),
            )
            .order_by(SysNoticeRead.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def add_receipt(self, notice_id: int, user_id: int, *, read_at: datetime) -> SysNoticeRead:
        """写入一条已读回执（调用方负责幂等预判与保存点）。

        Args:
            notice_id: 公告主键。
            user_id: 用户主键。
            read_at: 阅读时间（UTC）。

        Returns:
            SysNoticeRead: 已 flush 的回执行。

        Raises:
            IntegrityError: 并发重复插入（唯一约束兜底；调用方回滚保存点后重查）。
        """
        row = SysNoticeRead(notice_id=notice_id, user_id=user_id, read_at=read_at)
        self._session.add(row)
        await self._session.flush()
        return row

    async def read_count(self, notice_id: int) -> int:
        """统计某公告的已读人数（去重用户）。

        Args:
            notice_id: 公告主键。

        Returns:
            int: 已读人数。
        """
        statement = (
            select(func.count(func.distinct(SysNoticeRead.user_id)))
            .select_from(SysNoticeRead)
            .where(SysNoticeRead.notice_id == notice_id, SysNoticeRead.deleted_at.is_(None))
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def expired(self, *, now: datetime, limit: int) -> ConcurrentStableList[SysNotice]:
        """取到期未下线的公告（按过期时间升序）。

        Args:
            now: 当前 UTC 时间。
            limit: 单批上限。

        Returns:
            ConcurrentStableList[SysNotice]: 到期公告行。
        """
        statement = (
            self._select()
            .where(
                SysNotice.status == NOTICE_STATUS_PUBLISHED,
                SysNotice.expire_at.is_not(None),
                SysNotice.expire_at <= now,
            )
            .order_by(SysNotice.expire_at, SysNotice.id)
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableList(rows)

    async def mark_offline(self, row: SysNotice) -> bool:
        """把一行公告置为已下线（保存点 + 乐观锁；冲突即跳过）。

        Args:
            row: 已加载的公告行。

        Returns:
            bool: 本实例成功更新为 True；并发冲突 / 状态已变 False。
        """
        try:
            async with self._session.begin_nested():  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
                row.status = NOTICE_STATUS_OFFLINE
                await self._session.flush()
        except StaleDataError:
            return False
        return True

    async def _page(
        self, statement: Select[tuple[SysNotice]], *, page: int, size: int
    ) -> tuple[ConcurrentStableList[SysNotice], int]:
        """按固定公告排序取分页。

        Args:
            statement: 已带筛选条件的 select。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[SysNotice], int]: （当页记录, 总数）。
        """
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (await self._session.execute(statement.order_by(*self._order()).offset((page - 1) * size).limit(size)))
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    def _visible(self, statement: Select[tuple[SysNotice]], now: datetime) -> Select[tuple[SysNotice]]:
        """追加公告可见性条件（发布中 + 时间窗口）。

        Args:
            statement: 原 select。
            now: 当前 UTC 时间。

        Returns:
            Select[tuple[SysNotice]]: 追加条件后的 select。
        """
        return statement.where(
            SysNotice.status == NOTICE_STATUS_PUBLISHED,
            SysNotice.publish_at <= now,
            (SysNotice.expire_at.is_(None)) | (SysNotice.expire_at > now),
        )

    @staticmethod
    def _order() -> ConcurrentStableList[ColumnElement[object]]:
        """公告固定排序：置顶优先，置顶组按更新时间、非置顶组按发布时间。

        Returns:
            ConcurrentStableList[ColumnElement[object]]: order_by 参数。
        """
        return ConcurrentStableList(
            (
                cast("ColumnElement[object]", SysNotice.is_top.desc()),
                cast(
                    "ColumnElement[object]",
                    case((SysNotice.is_top.is_(True), SysNotice.updated_at), else_=SysNotice.publish_at).desc(),
                ),
                cast("ColumnElement[object]", SysNotice.id.desc()),
            )
        )
