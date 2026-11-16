"""邮件域仓储：模板分页 / 按 code 取、发送记录分页 / 按主键与幂等键取。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_notification.domains.notification.models.mail import SysMailLog, SysMailTemplate

__all__ = ["MailRepository"]


class MailRepository(BaseDbRepository[SysMailTemplate]):
    """邮件模板与发送记录仓储（模板主模型）。"""

    model = SysMailTemplate
    sortable_fields = ConcurrentStableSet({"created_at", "id", "updated_at", "code"})

    async def page_templates(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysMailTemplate], int]:
        """租户模板分页（code / 名称关键字 + 状态）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（code / 名称模糊匹配）。
            status: 状态（enabled / disabled）。

        Returns:
            tuple[ConcurrentStableList[SysMailTemplate], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if status:
            statement = statement.where(SysMailTemplate.status == status)
        if keyword:
            statement = statement.where(
                SysMailTemplate.code.contains(keyword, autoescape=True)
                | SysMailTemplate.name.contains(keyword, autoescape=True)
            )
        return await self._page(statement, page=page, size=size)

    async def list_templates(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> ConcurrentStableList[SysMailTemplate]:
        """列出全部租户模板（列表合并内置默认用；模板量级小）。

        Args:
            keyword: code / 名称关键字。
            status: 状态。

        Returns:
            ConcurrentStableList[SysMailTemplate]: 模板列表（按 code 升序）。
        """
        statement = self._select()
        if status:
            statement = statement.where(SysMailTemplate.status == status)
        if keyword:
            statement = statement.where(
                SysMailTemplate.code.contains(keyword, autoescape=True)
                | SysMailTemplate.name.contains(keyword, autoescape=True)
            )
        rows = (await self._session.execute(statement.order_by(SysMailTemplate.code.asc()))).scalars().all()
        return ConcurrentStableList(rows)

    async def get_template(self, template_id: int) -> SysMailTemplate | None:
        """按主键取租户模板（软删除过滤）。

        Args:
            template_id: 模板主键。

        Returns:
            SysMailTemplate | None: 模板；不存在为 None。
        """
        statement = self._select().where(SysMailTemplate.id == template_id)
        return (await self._session.execute(statement)).scalars().first()

    async def get_template_by_code(self, code: str) -> SysMailTemplate | None:
        """按 code 取租户模板（含停用；软删除过滤）。

        Args:
            code: 模板 code。

        Returns:
            SysMailTemplate | None: 模板；不存在为 None。
        """
        statement = self._select().where(SysMailTemplate.code == code)
        return (await self._session.execute(statement)).scalars().first()

    async def page_logs(
        self,
        *,
        page: int,
        size: int,
        status: str | None = None,
        template_code: str | None = None,
        recipient: str | None = None,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[ConcurrentStableList[SysMailLog], int]:
        """发送记录分页（按创建时间倒序）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            status: 状态筛选。
            template_code: 模板 code 筛选。
            recipient: 收件地址模糊筛选。
            user_id: 收件用户筛选。
            start_at: 创建时间下限（UTC）。
            end_at: 创建时间上限（UTC）。

        Returns:
            tuple[ConcurrentStableList[SysMailLog], int]: （当页记录, 总数）。
        """
        statement: Select[tuple[SysMailLog]] = select(SysMailLog).where(SysMailLog.deleted_at.is_(None))
        if status:
            statement = statement.where(SysMailLog.status == status)
        if template_code:
            statement = statement.where(SysMailLog.template_code == template_code)
        if recipient:
            statement = statement.where(SysMailLog.recipient.contains(recipient, autoescape=True))
        if user_id is not None:
            statement = statement.where(SysMailLog.user_id == user_id)
        if start_at is not None:
            statement = statement.where(SysMailLog.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(SysMailLog.created_at <= end_at)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(SysMailLog.created_at.desc(), SysMailLog.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def get_log(self, log_id: int) -> SysMailLog | None:
        """按主键取发送记录（软删除过滤）。

        Args:
            log_id: 记录主键。

        Returns:
            SysMailLog | None: 记录；不存在为 None。
        """
        statement = select(SysMailLog).where(SysMailLog.id == log_id, SysMailLog.deleted_at.is_(None))
        return (await self._session.execute(statement)).scalars().first()

    async def get_log_by_idempotency_key(self, idempotency_key: str) -> SysMailLog | None:
        """按幂等键取发送记录。

        Args:
            idempotency_key: 幂等键。

        Returns:
            SysMailLog | None: 记录；不存在为 None。
        """
        statement = select(SysMailLog).where(
            SysMailLog.idempotency_key == idempotency_key,
            SysMailLog.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _page(
        self, statement: Select[tuple[SysMailTemplate]], *, page: int, size: int
    ) -> tuple[ConcurrentStableList[SysMailTemplate], int]:
        """按更新时间倒序取模板分页。

        Args:
            statement: 已带筛选条件的 select。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[SysMailTemplate], int]: （当页记录, 总数）。
        """
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(SysMailTemplate.updated_at.desc(), SysMailTemplate.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total
