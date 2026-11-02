"""导入域只读仓储：`sys_job` / `sys_job_error`（状态与错误明细）。"""

from __future__ import annotations

from sqlalchemy import func, select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.job import SysJob, SysJobError
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

    async def count_errors(self, job_id: int) -> int:
        """统计错误明细条数。

        Args:
            job_id: 作业主键。

        Returns:
            int: 条数。
        """
        statement = select(func.count()).select_from(SysJobError).where(SysJobError.job_id == job_id)
        return int((await self._session.execute(statement)).scalar_one())
