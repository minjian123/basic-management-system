"""回收站超期清理服务：逐表批删 + 清理批次记录（同库同事务）。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import update

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import RecycleSettings
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.recycle import (
    RECYCLE_LOG_STATUS_FAILED,
    RECYCLE_LOG_STATUS_RUNNING,
    RECYCLE_LOG_STATUS_SUCCESS,
    SysRecycleLog,
)
from bms_core.recycle.engine import RecycleEngine
from bms_core.recycle.registry import recycle_table_specs

__all__ = ["RecyclePurgeService"]

_LOGGER = get_logger("bms.platform.recycle")


def _utc_now() -> datetime:
    """当前 UTC naive 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


class RecyclePurgeService(BaseFrameworkObject):
    """超期软删除数据物理清理（作业内执行）。"""

    def __init__(
        self,
        session: DbSession,
        settings: RecycleSettings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            settings: 回收站运行参数。
            clock: 当前时钟（测试可注入）。
        """
        self._session = session
        self._settings = settings
        self._clock = clock or _utc_now
        self._engine = RecycleEngine(session, settings, clock=self._clock)

    async def run(self) -> ConcurrentStableDict[str, object]:
        """逐表清理超期软删除数据并写批次记录。

        Returns:
            ConcurrentStableDict[str, object]: 汇总（`tables` / `deleted` / `failed`）。
        """
        now = self._clock()
        cutoff = now - timedelta(days=self._settings.retention_days)
        await self._reclaim_stale(now)
        batch_key = f"recycle:{now:%Y%m%d%H%M%S}:{uuid4().hex[:8]}"
        tables = 0
        deleted = 0
        failed = 0
        for spec in recycle_table_specs():
            tables += 1
            log = SysRecycleLog(
                batch_key=batch_key,
                table_name=spec.table,
                status=RECYCLE_LOG_STATUS_RUNNING,
                retention_days=self._settings.retention_days,
                cutoff_at=cutoff,
                started_at=now,
            )
            self._session.add(log)
            await self._session.commit()
            log_id = int(log.id)
            try:
                outcome = await self._engine.purge_table(spec.table, cutoff=cutoff)
                await self._finish(
                    log_id,
                    status=RECYCLE_LOG_STATUS_SUCCESS,
                    deleted_count=outcome.deleted_count,
                    detail=json.dumps(
                        {
                            "batch_size": self._settings.batch_size,
                            "max_rows": self._settings.max_batch_rows,
                            "batches": outcome.batches,
                        },
                        ensure_ascii=False,
                    ),
                )
                deleted += outcome.deleted_count
            except Exception as exc:  # 单表失败不影响其他表；作业最终失败可重试
                await self._session.rollback()
                failed += 1
                await self._finish(
                    log_id,
                    status=RECYCLE_LOG_STATUS_FAILED,
                    deleted_count=0,
                    error_msg=f"{type(exc).__name__}: {exc}"[:512],
                )
                _LOGGER.error("recycle_purge_table_failed", table=spec.table, error=repr(exc))
        return ConcurrentStableDict({"tables": tables, "deleted": deleted, "failed": failed})

    async def _finish(
        self,
        log_id: int,
        *,
        status: str,
        deleted_count: int,
        detail: str | None = None,
        error_msg: str | None = None,
    ) -> None:
        """回写单表清理结果。"""
        row = await self._session.get(SysRecycleLog, log_id)
        if row is None:  # pragma: no cover - 记录刚插入且已提交，缺失属数据库异常
            return
        now = self._clock()
        row.status = status
        row.deleted_count = deleted_count
        row.finished_at = now
        row.cost_time = max(0, int((now - row.started_at).total_seconds() * 1000))
        row.detail = detail
        row.error_msg = error_msg
        await self._session.commit()

    async def _reclaim_stale(self, now: datetime) -> None:
        """把超时 `running` 批次回收为 `failed`（进程中断兜底）。"""
        threshold = now - timedelta(minutes=self._settings.running_timeout_minutes)
        await self._session.execute(
            update(SysRecycleLog)
            .where(
                SysRecycleLog.status == RECYCLE_LOG_STATUS_RUNNING,
                SysRecycleLog.started_at < threshold,
                SysRecycleLog.deleted_at.is_(None),
            )
            .values(
                status=RECYCLE_LOG_STATUS_FAILED,
                error_msg="执行超时未完成（进程可能中断）",
                finished_at=now,
                cost_time=None,
            )
        )
        await self._session.commit()
