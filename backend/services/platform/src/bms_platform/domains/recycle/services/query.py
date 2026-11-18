"""回收站查询服务：模块计数 / 单表分页 / 详情 / 清理批次记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import RecycleSettings
from bms_core.core.exceptions import ParamError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.recycle import RECYCLE_LOG_STATUSES, SysRecycleLog
from bms_core.recycle.engine import RecycleEngine
from bms_core.recycle.spec import RecycleDetail, RecycleModule, RecyclePageRow

__all__ = ["RecycleQueryService"]


class RecycleQueryService(BaseFrameworkObject):
    """回收站只读服务（请求级会话）。"""

    def __init__(self, session: DbSession, settings: RecycleSettings) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            settings: 回收站运行参数。
        """
        self._session = session
        self._engine = RecycleEngine(session, settings)

    async def modules(self) -> ConcurrentStableList[RecycleModule]:
        """模块 / 表清单与删除计数。

        Returns:
            ConcurrentStableList[RecycleModule]: 模块分组。
        """
        return ConcurrentStableList(await self._engine.modules())

    async def page(
        self,
        table_name: str,
        *,
        keyword: str | None,
        deleted_from: datetime | None,
        deleted_to: datetime | None,
        page: int,
        size: int,
    ) -> tuple[ConcurrentStableList[RecyclePageRow], int]:
        """单表分页。

        Args:
            table_name: 逻辑表名。
            keyword: 关键字。
            deleted_from: 删除时间下界。
            deleted_to: 删除时间上界。
            page: 页码。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[RecyclePageRow], int]: 行与总数。
        """
        rows, total = await self._engine.page(
            table_name,
            keyword=keyword,
            deleted_from=deleted_from,
            deleted_to=deleted_to,
            page=page,
            size=size,
        )
        return ConcurrentStableList(rows), total

    async def detail(self, table_name: str, row_id: int) -> RecycleDetail:
        """单行详情。

        Args:
            table_name: 逻辑表名。
            row_id: 主键。

        Returns:
            RecycleDetail: 详情。
        """
        return await self._engine.detail(table_name, row_id)

    async def cleanups(
        self,
        *,
        table_name: str | None,
        status: str | None,
        started_from: datetime | None,
        started_to: datetime | None,
        page: int,
        size: int,
    ) -> tuple[ConcurrentStableList[SysRecycleLog], int]:
        """清理批次记录分页。

        Args:
            table_name: 表名筛选。
            status: 状态筛选（running / success / failed）。
            started_from: 开始时间下界。
            started_to: 开始时间上界。
            page: 页码。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[SysRecycleLog], int]: 行与总数。

        Raises:
            ParamError: 状态非法或时间范围起止颠倒（10001）。
        """
        if status is not None and status not in RECYCLE_LOG_STATUSES:
            raise ParamError(f"清理批次状态非法：{status}")
        if started_from is not None and started_to is not None and started_from > started_to:
            raise ParamError("开始时间范围起止颠倒")
        conditions: ConcurrentStableList[Any] = ConcurrentStableList((SysRecycleLog.deleted_at.is_(None),))
        if table_name:
            conditions.add(SysRecycleLog.table_name == table_name)
        if status:
            conditions.add(SysRecycleLog.status == status)
        if started_from is not None:
            conditions.add(SysRecycleLog.started_at >= started_from)
        if started_to is not None:
            conditions.add(SysRecycleLog.started_at <= started_to)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(SysRecycleLog).where(*conditions))
            ).scalar_one()
        )
        statement = (
            select(SysRecycleLog)
            .where(*conditions)
            .order_by(SysRecycleLog.started_at.desc(), SysRecycleLog.id.desc())
            .limit(size)
            .offset((page - 1) * size)
        )
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        return rows, total
