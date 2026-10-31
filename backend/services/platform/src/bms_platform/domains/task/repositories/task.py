"""任务调度域仓储：任务定义筛选分页 + 乐观锁更新 + 执行记录分页。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, func, select, update

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.task import SysTask, SysTaskLog
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["TaskLogRepository", "TaskRepository"]


class TaskRepository(BaseDbRepository[SysTask]):
    """任务定义仓储（`sys_task`）。"""

    model = SysTask
    sortable_fields = ConcurrentStableSet({"id", "code", "name", "status", "next_run_at"})

    async def get_by_code(self, code: str) -> SysTask | None:
        """按任务代码取记录（软删除后不可见）。

        Args:
            code: 任务代码。

        Returns:
            SysTask | None: 记录；不存在 None。
        """
        statement = self._select().where(self._column("code") == code)
        return (await self._session.execute(statement)).scalars().first()

    async def get_by_name(self, name: str) -> SysTask | None:
        """按任务名取记录（软删除后不可见）。

        Args:
            name: 任务名。

        Returns:
            SysTask | None: 记录；不存在 None。
        """
        statement = self._select().where(self._column("name") == name)
        return (await self._session.execute(statement)).scalars().first()

    async def page_filtered(
        self, *, page: int, size: int, name: str | None = None, status: str | None = None
    ) -> tuple[ConcurrentStableList[SysTask], int]:
        """按名称关键字 / 状态筛选分页。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            name: 名称关键字（模糊匹配）。
            status: 状态精确匹配。

        Returns:
            tuple[ConcurrentStableList[SysTask], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if name:
            statement = statement.where(self._column("name").like(f"%{name}%"))
        if status:
            statement = statement.where(self._column("status") == status)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("id").desc()).offset((page - 1) * size).limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """带乐观锁的字段更新（`version` 不匹配即拒绝）。

        Args:
            item_id: 任务主键。
            expected_version: 期望版本（取详情里的当前值）。
            now: 当前时刻（UTC naive）。
            **values: 待更新字段。

        Returns:
            bool: 更新成功 True；版本不匹配 / 记录不存在 False。
        """
        payload = dict(values)
        payload["updated_at"] = now
        payload["version"] = expected_version + 1
        statement = (
            update(SysTask)
            .where(
                SysTask.id == item_id,
                SysTask.version == expected_version,
                SysTask.deleted_at.is_(None),
            )
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1


class TaskLogRepository(BaseDbRepository[SysTaskLog]):
    """执行记录仓储（`sys_task_log`）。"""

    model = SysTaskLog
    sortable_fields = ConcurrentStableSet({"id", "started_at"})

    async def page_by_task(self, *, task_id: int, page: int, size: int) -> tuple[ConcurrentStableList[SysTaskLog], int]:
        """按任务取执行记录（按开始时间倒序）。

        Args:
            task_id: 任务主键。
            page: 页码（从 1 起）。
            size: 每页条数。

        Returns:
            tuple[ConcurrentStableList[SysTaskLog], int]: （当页记录, 总数）。
        """
        statement = self._select().where(self._column("task_id") == task_id)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("started_at").desc(), self._column("id").desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total
