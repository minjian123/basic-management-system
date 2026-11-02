"""导入域只读仓储：`sys_job` / `sys_job_error`（状态与错误明细）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.job import JOB_STATUS_SUCCEEDED, SysJob, SysJobError
from bms_core.repositories.base_db_repository import BaseDbRepository

__all__ = ["ImportJobRepository"]


class ImportJobRepository(BaseDbRepository[SysJob]):
    """导入作业读侧（租户库；作业与错误明细同库）。"""

    model = SysJob

    async def get_job(self, job_id: int) -> SysJob | None:
        """按主键取作业。

        Args:
            job_id: 作业主键。

        Returns:
            SysJob | None: 作业记录；不存在返回 None。
        """
        return await self.get(job_id)

    async def list_errors(self, job_id: int, *, limit: int, offset: int = 0) -> ConcurrentStableList[SysJobError]:
        """按行号取前 N 条错误明细。

        Args:
            job_id: 作业主键。
            limit: 条数上限。
            offset: 偏移。

        Returns:
            ConcurrentStableList[SysJobError]: 错误明细（按行号 / 主键升序）。
        """
        statement = (
            select(SysJobError)
            .where(SysJobError.job_id == job_id)
            .order_by(SysJobError.row_no.asc(), SysJobError.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_all_errors(self, job_id: int) -> ConcurrentStableList[SysJobError]:
        """取该作业全部错误明细（错误明细下载用）。

        Args:
            job_id: 作业主键。

        Returns:
            ConcurrentStableList[SysJobError]: 全部错误明细。
        """
        statement = (
            select(SysJobError)
            .where(SysJobError.job_id == job_id)
            .order_by(SysJobError.row_no.asc(), SysJobError.id.asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_succeeded_before(
        self,
        job_type: str,
        before: datetime,
        *,
        limit: int,
        offset: int = 0,
    ) -> ConcurrentStableList[SysJob]:
        """按类型 + 成功终态 + 完成时间取过期作业（导出产物清理用）。

        过滤全部下推到 SQL（类型 / 状态 / 完成时间三列），产物 key 是否存在于 `result` 由应用层判定
        （JSON 列跨方言语法不一致，不在 SQL 层解析）。

        Args:
            job_type: 作业类型。
            before: 完成时间上界（UTC naive；早于该时刻视为过期）。
            limit: 单批上限。
            offset: 偏移（分批推进；已标记 `expired_at` 的行仍会被扫到，由调用方按批推进）。

        Returns:
            ConcurrentStableList[SysJob]: 作业记录（按完成时间升序）。
        """
        statement = (
            select(SysJob)
            .where(
                SysJob.job_type == job_type,
                SysJob.status == JOB_STATUS_SUCCEEDED,
                SysJob.finished_at.is_not(None),
                SysJob.finished_at < before,
            )
            .order_by(SysJob.finished_at.asc(), SysJob.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_errors(self, job_id: int) -> int:
        """统计错误明细条数。

        Args:
            job_id: 作业主键。

        Returns:
            int: 条数。
        """
        statement = select(func.count()).select_from(SysJobError).where(SysJobError.job_id == job_id)
        return int((await self._session.execute(statement)).scalar_one())
