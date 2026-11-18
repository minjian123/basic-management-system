"""回收站作业：超期软删除数据物理清理。"""

from __future__ import annotations

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.db.session import DbSession
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_platform.domains.recycle.services.purge import RecyclePurgeService

__all__ = ["RecyclePurgeJob"]


class RecyclePurgeJob(BaseJobHandler):
    """超期软删除数据清理作业（按租户执行，逐表批删并记录）。"""

    job_type = "platform.recycle.purge"
    description = "清理超过保留期的软删除数据（逐表批删，写 sys_recycle_log）"

    async def run(self, ctx: JobContext) -> JobResult:
        """执行清理。

        Args:
            ctx: 作业上下文（会话绑定任务行的租户库）。

        Returns:
            JobResult: 成功含汇总；任一张表失败可重试。
        """
        settings = get_settings()
        async with ctx.session() as session:
            service = RecyclePurgeService(cast("DbSession", session), settings.recycle_options)
            summary = await service.run()
        failed = int(str(summary.get("failed", 0)))
        message = (
            f"回收站清理完成：表 {summary.get('tables', 0)} 张，删除 {summary.get('deleted', 0)} 条，失败 {failed} 张"
        )
        output: ConcurrentStableDict[str, object] = ConcurrentStableDict(summary)
        if failed:
            return JobResult.failed(message, retryable=True, output=output)
        return JobResult.success(output, message=message)
