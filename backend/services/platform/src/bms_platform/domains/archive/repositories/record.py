"""归档数据行仓储（归档库 `bms_archive`）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import SysArchiveRecord

__all__ = ["ArchiveRecordRepository"]


class ArchiveRecordRepository(BaseFrameworkObject):
    """归档行读写（事务边界归调用方）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 归档库会话。
        """
        self._session = session

    async def existing_source_ids(
        self, source_table: str, source_ids: ConcurrentStableList[str]
    ) -> ConcurrentStableSet[str]:
        """取本批中已归档的源主键（幂等预判）。

        Args:
            source_table: 源逻辑表名。
            source_ids: 源行主键清单。

        Returns:
            ConcurrentStableSet[str]: 已存在的源主键集合。
        """
        if not source_ids:
            return ConcurrentStableSet()
        result = await self._session.execute(
            select(SysArchiveRecord.source_id).where(
                SysArchiveRecord.source_table == source_table,
                SysArchiveRecord.source_id.in_(list(source_ids)),
            )
        )
        return ConcurrentStableSet(str(value) for value in result.scalars().all())

    async def insert_many(self, rows: ConcurrentStableList[SysArchiveRecord]) -> int:
        """批量写入归档行。

        Args:
            rows: 归档行实体。

        Returns:
            int: 写入条数。
        """
        if not rows:
            return 0
        for row in rows:
            self._session.add(row)
        await self._session.flush()
        return len(rows)

    async def get_by_source(self, source_table: str, source_id: str) -> SysArchiveRecord | None:
        """按源表 + 源主键取归档行。

        Args:
            source_table: 源逻辑表名。
            source_id: 源行主键。

        Returns:
            SysArchiveRecord | None: 命中返回归档行。
        """
        result = await self._session.execute(
            select(SysArchiveRecord).where(
                SysArchiveRecord.source_table == source_table,
                SysArchiveRecord.source_id == source_id,
            )
        )
        return result.scalar_one_or_none()

    async def page(
        self,
        *,
        page: int,
        size: int,
        source_table: str | None = None,
        source_id: str | None = None,
        source_month: str | None = None,
        tenant_id: int | None = None,
        stored_from: datetime | None = None,
        stored_to: datetime | None = None,
    ) -> tuple[ConcurrentStableList[SysArchiveRecord], int]:
        """分页查询归档行。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            source_table: 源表筛选。
            source_id: 源主键筛选。
            source_month: 源分片月份筛选。
            tenant_id: 租户筛选（None = 不限制，仅审计管理员路径）。
            stored_from: 归档时间下限（UTC）。
            stored_to: 归档时间上限（UTC）。

        Returns:
            tuple[ConcurrentStableList[SysArchiveRecord], int]: （当前页, 总数）。
        """
        conditions: ConcurrentStableList[Any] = ConcurrentStableList()
        if source_table:
            conditions.append(SysArchiveRecord.source_table == source_table)
        if source_id:
            conditions.append(SysArchiveRecord.source_id == source_id)
        if source_month:
            conditions.append(SysArchiveRecord.source_month == source_month)
        if tenant_id is not None:
            conditions.append(SysArchiveRecord.tenant_id == tenant_id)
        if stored_from is not None:
            conditions.append(SysArchiveRecord.archived_at >= stored_from)
        if stored_to is not None:
            conditions.append(SysArchiveRecord.archived_at <= stored_to)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(SysArchiveRecord).where(*conditions))
            ).scalar_one()
        )
        result = await self._session.execute(
            select(SysArchiveRecord)
            .where(*conditions)
            .order_by(SysArchiveRecord.archived_at.desc(), SysArchiveRecord.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return ConcurrentStableList(result.scalars().all()), total

    async def expired(self, *, policy_id: int, before: datetime, limit: int) -> ConcurrentStableList[SysArchiveRecord]:
        """取满保留期的归档行（冷化扫描）。

        Args:
            policy_id: 策略主键。
            before: 归档时间早于该时刻（UTC）。
            limit: 单批上限。

        Returns:
            ConcurrentStableList[SysArchiveRecord]: 归档行。
        """
        result = await self._session.execute(
            select(SysArchiveRecord)
            .where(SysArchiveRecord.policy_id == policy_id, SysArchiveRecord.archived_at <= before)
            .order_by(SysArchiveRecord.tenant_id, SysArchiveRecord.archived_at, SysArchiveRecord.id)
            .limit(limit)
        )
        return ConcurrentStableList(result.scalars().all())

    async def delete_ids(self, ids: ConcurrentStableList[int]) -> int:
        """按主键批量删除归档行。

        Args:
            ids: 归档行主键。

        Returns:
            int: 删除条数。
        """
        if not ids:
            return 0
        result = await self._session.execute(delete(SysArchiveRecord).where(SysArchiveRecord.id.in_(list(ids))))
        return int(getattr(result, "rowcount", 0) or 0)
