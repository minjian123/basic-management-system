"""归档执行记录仓储（平台库）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.archive import (
    ARCHIVE_LOG_STATUS_FAILED,
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_TARGET_MINIO,
    SysArchiveLog,
)

__all__ = ["ArchiveLogRepository"]


class ArchiveLogRepository(BaseFrameworkObject):
    """归档执行记录读写（事务边界归调用方）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 平台库会话。
        """
        self._session = session

    async def get(self, log_id: int) -> SysArchiveLog | None:
        """按主键取执行记录。

        Args:
            log_id: 记录主键。

        Returns:
            SysArchiveLog | None: 命中返回记录。
        """
        result = await self._session.execute(
            select(SysArchiveLog).where(SysArchiveLog.id == log_id, SysArchiveLog.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def page(
        self,
        *,
        page: int,
        size: int,
        policy_id: int | None = None,
        table_name: str | None = None,
        target: str | None = None,
        status: str | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> tuple[ConcurrentStableList[SysArchiveLog], int]:
        """分页查询执行记录。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            policy_id: 策略筛选。
            table_name: 表名筛选。
            target: 目标筛选。
            status: 状态筛选。
            started_from: 开始时间下限（UTC）。
            started_to: 开始时间上限（UTC）。

        Returns:
            tuple[ConcurrentStableList[SysArchiveLog], int]: （当前页, 总数）。
        """
        conditions: ConcurrentStableList[Any] = ConcurrentStableList((SysArchiveLog.deleted_at.is_(None),))
        if policy_id is not None:
            conditions.append(SysArchiveLog.policy_id == policy_id)
        if table_name:
            conditions.append(SysArchiveLog.table_name == table_name)
        if target:
            conditions.append(SysArchiveLog.target == target)
        if status:
            conditions.append(SysArchiveLog.status == status)
        if started_from is not None:
            conditions.append(SysArchiveLog.started_at >= started_from)
        if started_to is not None:
            conditions.append(SysArchiveLog.started_at <= started_to)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(SysArchiveLog).where(*conditions))
            ).scalar_one()
        )
        result = await self._session.execute(
            select(SysArchiveLog)
            .where(*conditions)
            .order_by(SysArchiveLog.started_at.desc(), SysArchiveLog.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        return ConcurrentStableList(result.scalars().all()), total

    async def add(self, log: SysArchiveLog) -> SysArchiveLog:
        """新增执行记录并 flush（取得主键）。

        Args:
            log: 记录实体。

        Returns:
            SysArchiveLog: 已 flush 的记录。
        """
        self._session.add(log)
        await self._session.flush()
        return log

    async def finish(
        self,
        log_id: int,
        *,
        status: str,
        finished_at: datetime,
        cost_time: int,
        archived_count: int,
        error_msg: str | None = None,
        detail: str | None = None,
        file_key: str | None = None,
        retention_until: datetime | None = None,
    ) -> None:
        """回写执行记录终态。

        Args:
            log_id: 记录主键。
            status: 终态。
            finished_at: 结束时间（UTC）。
            cost_time: 耗时（毫秒）。
            archived_count: 本次处理条数。
            error_msg: 失败摘要。
            detail: 明细 JSON。
            file_key: 冷化对象 key。
            retention_until: 冷化文件保留到期时刻。
        """
        log = await self.get(log_id)
        if log is None:
            return
        log.status = status
        log.finished_at = finished_at
        log.cost_time = cost_time
        log.archived_count = archived_count
        log.error_msg = error_msg
        log.detail = detail
        if file_key is not None:
            log.file_key = file_key
        if retention_until is not None:
            log.retention_until = retention_until
        await self._session.flush()

    async def running(self, policy_id: int) -> bool:
        """策略是否有执行中的批次。

        Args:
            policy_id: 策略主键。

        Returns:
            bool: 存在 `running` 记录返回 True。
        """
        result = await self._session.execute(
            select(SysArchiveLog.id)
            .where(
                SysArchiveLog.policy_id == policy_id,
                SysArchiveLog.status == ARCHIVE_LOG_STATUS_RUNNING,
                SysArchiveLog.deleted_at.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def reclaim_stale(self, before: datetime) -> int:
        """把超时未完成的 `running` 记录回收为失败。

        Args:
            before: 开始时间早于该时刻视为超时（UTC）。

        Returns:
            int: 回收条数。
        """
        result = await self._session.execute(
            select(SysArchiveLog).where(
                SysArchiveLog.status == ARCHIVE_LOG_STATUS_RUNNING,
                SysArchiveLog.started_at < before,
                SysArchiveLog.deleted_at.is_(None),
            )
        )
        rows = ConcurrentStableList(result.scalars().all())
        for row in rows:
            row.status = ARCHIVE_LOG_STATUS_FAILED
            row.error_msg = "执行超时回收（worker 未回写终态）"
            row.finished_at = before
        if rows:
            await self._session.flush()
        return len(rows)

    async def pending_cleanup(self, now: datetime, *, limit: int) -> ConcurrentStableList[SysArchiveLog]:
        """取可清理的冷化文件记录（到期且未处置）。

        Args:
            now: 当前时刻（UTC）。
            limit: 单批上限。

        Returns:
            ConcurrentStableList[SysArchiveLog]: 待清理记录。
        """
        result = await self._session.execute(
            select(SysArchiveLog)
            .where(
                SysArchiveLog.target == ARCHIVE_TARGET_MINIO,
                SysArchiveLog.status == ARCHIVE_LOG_STATUS_SUCCESS,
                SysArchiveLog.retention_until.is_not(None),
                SysArchiveLog.retention_until <= now,
                SysArchiveLog.file_key.is_not(None),
                SysArchiveLog.disposed_at.is_(None),
                SysArchiveLog.deleted_at.is_(None),
            )
            .order_by(SysArchiveLog.retention_until, SysArchiveLog.id)
            .limit(limit)
        )
        return ConcurrentStableList(result.scalars().all())

    async def mark_disposed(self, log_id: int, *, dispose_type: str, now: datetime) -> None:
        """标记冷化文件已处置（幂等）。

        Args:
            log_id: 记录主键。
            dispose_type: 处置类型（cleanup / destroy）。
            now: 处置时刻（UTC）。
        """
        log = await self.get(log_id)
        if log is None or log.disposed_at is not None:
            return
        log.disposed_at = now
        log.dispose_type = dispose_type
        await self._session.flush()
