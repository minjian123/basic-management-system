"""短信域仓储：模板分页 / 按 code+渠道取、发送记录分页 / 按主键与幂等键取。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_notification.domains.notification.models.sms import SysSmsLog, SysSmsTemplate

__all__ = ["SmsRepository"]


class SmsRepository(BaseDbRepository[SysSmsTemplate]):
    """短信模板与发送记录仓储（模板主模型）。"""

    model = SysSmsTemplate
    sortable_fields = ConcurrentStableSet({"created_at", "id", "updated_at", "code"})

    async def page_templates(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
        channel: str | None = None,
        scene: str | None = None,
    ) -> tuple[ConcurrentStableList[SysSmsTemplate], int]:
        """租户短信模板分页。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: code / 名称关键字。
            status: 状态。
            channel: 渠道。
            scene: 场景。

        Returns:
            tuple[ConcurrentStableList[SysSmsTemplate], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if status:
            statement = statement.where(SysSmsTemplate.status == status)
        if channel:
            statement = statement.where(SysSmsTemplate.channel == channel)
        if scene:
            statement = statement.where(SysSmsTemplate.scene == scene)
        if keyword:
            statement = statement.where(
                SysSmsTemplate.code.contains(keyword, autoescape=True)
                | SysSmsTemplate.name.contains(keyword, autoescape=True)
            )
        return await self._page(statement, page=page, size=size)

    async def list_templates(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        channel: str | None = None,
        scene: str | None = None,
    ) -> ConcurrentStableList[SysSmsTemplate]:
        """列出全部租户短信模板（列表合并内置默认用）。"""
        statement = self._select()
        if status:
            statement = statement.where(SysSmsTemplate.status == status)
        if channel:
            statement = statement.where(SysSmsTemplate.channel == channel)
        if scene:
            statement = statement.where(SysSmsTemplate.scene == scene)
        if keyword:
            statement = statement.where(
                SysSmsTemplate.code.contains(keyword, autoescape=True)
                | SysSmsTemplate.name.contains(keyword, autoescape=True)
            )
        rows = (await self._session.execute(statement.order_by(SysSmsTemplate.code.asc()))).scalars().all()
        return ConcurrentStableList(rows)

    async def get_template(self, template_id: int) -> SysSmsTemplate | None:
        """按主键取租户模板。"""
        statement = self._select().where(SysSmsTemplate.id == template_id)
        return (await self._session.execute(statement)).scalars().first()

    async def get_template_by_code(self, code: str, channel: str) -> SysSmsTemplate | None:
        """按 code + 渠道取租户模板（含停用；软删除过滤）。"""
        statement = self._select().where(SysSmsTemplate.code == code, SysSmsTemplate.channel == channel)
        return (await self._session.execute(statement)).scalars().first()

    async def page_logs(
        self,
        *,
        page: int,
        size: int,
        status: str | None = None,
        channel: str | None = None,
        scene: str | None = None,
        template_code: str | None = None,
        recipient: str | None = None,
        user_id: int | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> tuple[ConcurrentStableList[SysSmsLog], int]:
        """发送记录分页（按创建时间倒序）。"""
        statement: Select[tuple[SysSmsLog]] = select(SysSmsLog).where(SysSmsLog.deleted_at.is_(None))
        if status:
            statement = statement.where(SysSmsLog.status == status)
        if channel:
            statement = statement.where(SysSmsLog.channel == channel)
        if scene:
            statement = statement.where(SysSmsLog.scene == scene)
        if template_code:
            statement = statement.where(SysSmsLog.template_code == template_code)
        if recipient:
            statement = statement.where(SysSmsLog.recipient.contains(recipient, autoescape=True))
        if user_id is not None:
            statement = statement.where(SysSmsLog.user_id == user_id)
        if start_at is not None:
            statement = statement.where(SysSmsLog.created_at >= start_at)
        if end_at is not None:
            statement = statement.where(SysSmsLog.created_at <= end_at)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(SysSmsLog.created_at.desc(), SysSmsLog.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def get_log(self, log_id: int) -> SysSmsLog | None:
        """按主键取发送记录。"""
        statement = select(SysSmsLog).where(SysSmsLog.id == log_id, SysSmsLog.deleted_at.is_(None))
        return (await self._session.execute(statement)).scalars().first()

    async def get_log_by_idempotency_key(self, idempotency_key: str) -> SysSmsLog | None:
        """按幂等键取发送记录。"""
        statement = select(SysSmsLog).where(
            SysSmsLog.idempotency_key == idempotency_key,
            SysSmsLog.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def _page(
        self, statement: Select[tuple[SysSmsTemplate]], *, page: int, size: int
    ) -> tuple[ConcurrentStableList[SysSmsTemplate], int]:
        """按更新时间倒序取模板分页。"""
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(SysSmsTemplate.updated_at.desc(), SysSmsTemplate.id.desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total
