"""作业中心平台侧仓储：类型目录与监控投影（均落平台库）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CursorResult, delete, func, select, update

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.job import (
    JOB_TYPE_STATUS_RETIRED,
    SysJobMonitor,
    SysJobType,
)
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["JobMonitorRepository", "JobTypeRepository"]


class JobTypeRepository(BaseDbRepository[SysJobType]):
    """作业类型目录仓储（`sys_job_type`，声明只读投影）。"""

    model = SysJobType
    sortable_fields = ConcurrentStableSet({"id", "job_type", "service_key", "status", "created_at"})

    async def get_by_type(self, job_type: str) -> SysJobType | None:
        """按作业类型取目录行（软删除后不可见）。

        Args:
            job_type: 作业类型。

        Returns:
            SysJobType | None: 目录行；不存在 None。
        """
        statement = self._select().where(self._column("job_type") == job_type)
        return (await self._session.execute(statement)).scalars().first()

    async def list_all(self) -> ConcurrentStableList[SysJobType]:
        """取全部目录行（按类型排序）。

        Returns:
            ConcurrentStableList[SysJobType]: 目录行。
        """
        statement = self._select().order_by(self._column("job_type").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def page_filtered(
        self, *, page: int, size: int, service_key: str | None = None, status: str | None = None
    ) -> tuple[ConcurrentStableList[SysJobType], int]:
        """按服务 / 状态筛选分页。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            service_key: 提供方服务键筛选。
            status: 目录状态筛选。

        Returns:
            tuple[ConcurrentStableList[SysJobType], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if service_key:
            statement = statement.where(self._column("service_key") == service_key)
        if status:
            statement = statement.where(self._column("status") == status)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("job_type").asc()).offset((page - 1) * size).limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def create_declaration(self, **values: object) -> SysJobType:
        """插入一条目录行。

        Args:
            **values: 目录字段。

        Returns:
            SysJobType: 新行。
        """
        record = SysJobType(**values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def update_declaration(self, job_type: str, *, now: datetime, **values: object) -> bool:
        """更新目录行（按作业类型）。

        Args:
            job_type: 作业类型。
            now: 当前时刻。
            **values: 待更新字段。

        Returns:
            bool: 更新成功 True。
        """
        payload = dict(values)
        payload["updated_at"] = now
        payload["version"] = SysJobType.version + 1
        statement = (
            update(SysJobType)
            .where(SysJobType.job_type == job_type, SysJobType.deleted_at.is_(None))
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1

    async def retire_missing(self, *, known_types: ConcurrentStableSet[str], now: datetime) -> int:
        """把本次声明未出现的目录行置为退役（不删行，历史作业仍可解释）。

        Args:
            known_types: 本次声明覆盖的作业类型集合。
            now: 当前时刻。

        Returns:
            int: 退役条数。
        """
        statement = (
            update(SysJobType)
            .where(
                SysJobType.deleted_at.is_(None),
                SysJobType.status != JOB_TYPE_STATUS_RETIRED,
                SysJobType.job_type.not_in(list(known_types)),
            )
            .values(status=JOB_TYPE_STATUS_RETIRED, updated_at=now, version=SysJobType.version + 1)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return int(result.rowcount)


class JobMonitorRepository(BaseDbRepository[SysJobMonitor]):
    """作业监控投影仓储（`sys_job_monitor`）。"""

    model = SysJobMonitor
    sortable_fields = ConcurrentStableSet({"id", "job_id", "status", "last_event_at"})

    async def get_by_job_id(self, job_id: int) -> SysJobMonitor | None:
        """按作业主键取投影行。

        Args:
            job_id: 作业主键。

        Returns:
            SysJobMonitor | None: 投影行；不存在 None。
        """
        statement = self._select().where(self._column("job_id") == job_id)
        return (await self._session.execute(statement)).scalars().first()

    async def page_filtered(
        self,
        *,
        page: int,
        size: int,
        job_type: str | None = None,
        status: str | None = None,
        service_key: str | None = None,
        tenant_id: int | None = None,
    ) -> tuple[ConcurrentStableList[SysJobMonitor], int]:
        """按类型 / 状态 / 服务 / 租户筛选分页（最近事件倒序）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            job_type: 作业类型筛选。
            status: 状态筛选。
            service_key: 提供方服务筛选。
            tenant_id: 租户主键筛选。

        Returns:
            tuple[ConcurrentStableList[SysJobMonitor], int]: （当页记录, 总数）。
        """
        statement = self._select()
        if job_type:
            statement = statement.where(self._column("job_type") == job_type)
        if status:
            statement = statement.where(self._column("status") == status)
        if service_key:
            statement = statement.where(self._column("service_key") == service_key)
        if tenant_id is not None:
            statement = statement.where(self._column("tenant_id") == tenant_id)
        total = int((await self._session.execute(select(func.count()).select_from(statement.subquery()))).scalar_one())
        rows = (
            (
                await self._session.execute(
                    statement.order_by(self._column("last_event_at").desc(), self._column("id").desc())
                    .offset((page - 1) * size)
                    .limit(size)
                )
            )
            .scalars()
            .all()
        )
        return ConcurrentStableList(rows), total

    async def create_projection(self, **values: object) -> SysJobMonitor:
        """插入一条投影行。

        Args:
            **values: 投影字段。

        Returns:
            SysJobMonitor: 新行。
        """
        record = SysJobMonitor(**values)
        self._session.add(record)
        await self._session.flush()
        return record

    async def update_projection(self, job_id: int, *, now: datetime, **values: object) -> bool:
        """更新投影行（按作业主键）。

        Args:
            job_id: 作业主键。
            now: 当前时刻。
            **values: 待更新字段。

        Returns:
            bool: 更新成功 True。
        """
        payload = dict(values)
        payload["updated_at"] = now
        payload["version"] = SysJobMonitor.version + 1
        statement = (
            update(SysJobMonitor)
            .where(SysJobMonitor.job_id == job_id, SysJobMonitor.deleted_at.is_(None))
            .values(**payload)
        )
        result: CursorResult[object] = await self._session.execute(statement)  # pyright: ignore[reportAssignmentType]
        return result.rowcount == 1

    async def delete_expired(self, *, cutoff: datetime) -> int:
        """删除超过保留期的投影行。

        Args:
            cutoff: 最近事件时间阈值（早于该时刻删除）。

        Returns:
            int: 删除条数。
        """
        result: CursorResult[object] = await self._session.execute(  # pyright: ignore[reportAssignmentType]
            delete(SysJobMonitor).where(SysJobMonitor.last_event_at < cutoff)
        )
        return int(result.rowcount)
