"""账本保留期清理：**只删终态且超期**的主记录（连同其分支）与超期处置台账（就地物理删除）。

口径（详设 05_07 §3.5）：

- **仅终态**：在途事务（`active` / `preparing` / `committing` / `rolling_back`）**一律不清理**——
  必须先由恢复器驱动至终态，否则会破坏「决定点后所有分支最终必须 commit」的不变量；
- **就地物理删除**（不迁归档表）：主记录按 `updated_at < cutoff`、台账按 `detected_at < cutoff`；
  分支随所属事务同批删除（避免孤儿）；
- **执行方**：仅 leader（并入恢复器常驻任务同一轮）；手工兜底 `ops/txn_recovery.py cleanup`；
- **留痕**：不写 `txn_global_recovery`（该表自身即清理对象），以指标 `bms_txn_cleaned_total{scope}`
  与结构化日志留痕。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.metrics.base import BaseMetrics
from bms_txn.models.ledger import GlobalTxn
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)

__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "METRIC_CLEANED",
    "CleanupStats",
    "LedgerCleanup",
]

_LOGGER = get_logger("bms.txn.cleanup")

DEFAULT_RETENTION_DAYS = 30
"""账本保留期缺省值（天；`[transaction_manager].ledger_retention_days`）。"""

METRIC_CLEANED = "bms_txn_cleaned_total"
"""指标：账本清理删除行数（按对象 `global` / `branch` / `recovery`）。"""


@dataclass(frozen=True)
class CleanupStats(BaseValueObject):
    """单轮清理统计（值对象）。"""

    globals: int = 0
    """全局事务主记录行数（删除数；`dry_run` 下为将删除数）。"""

    branches: int = 0
    """分支行数（随主记录同批）。"""

    recoveries: int = 0
    """处置台账行数。"""

    @property
    def total(self) -> int:
        """合计行数。"""
        return self.globals + self.branches + self.recoveries


class LedgerCleanup(BaseFrameworkObject):
    """账本保留期清理器（单轮；仅终态超期，就地物理删除）。"""

    def __init__(
        self,
        txns: GlobalTxnRepository,
        branches: GlobalTxnBranchRepository,
        recoveries: GlobalTxnRecoveryRepository,
        uow: UnitOfWork,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        batch_limit: int = 200,
        recovery_batch_limit: int = 500,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            txns: 全局事务主记录仓储。
            branches: 分支仓储。
            recoveries: 处置台账仓储。
            uow: 工作单元（**平台库**写会话）。
            retention_days: 保留期（天；终态 / 台账超此期即清理）。
            batch_limit: 单轮主记录上限（连同其分支）。
            recovery_batch_limit: 单轮台账上限。
            metrics: 指标出口（None 不上报）。
        """
        self._txns = txns
        self._branches = branches
        self._recoveries = recoveries
        self._uow = uow
        self._retention_days = retention_days
        self._batch_limit = batch_limit
        self._recovery_batch_limit = recovery_batch_limit
        self._metrics = metrics

    async def run_once(self, *, now: datetime | None = None, dry_run: bool = False) -> CleanupStats:
        """单轮清理：终态超期主记录（含分支）→ 超期处置台账。

        Args:
            now: 当前时间（UTC；缺省取系统时钟；用例可注入）。
            dry_run: 只统计不删除（`ops txn_recovery cleanup --dry-run` 用）。

        Returns:
            CleanupStats: 本轮删除（`dry_run` 下为**将删除**）的行数统计。
        """
        moment = now if now is not None else datetime.now(UTC)
        cutoff = moment - timedelta(days=self._retention_days)
        async with self._uow.begin():
            expired = await self._txns.list_terminal_before(cutoff=cutoff, limit=self._batch_limit)
            expired_recoveries = await self._recoveries.list_before(cutoff=cutoff, limit=self._recovery_batch_limit)
            if dry_run:
                stats = CleanupStats(
                    globals=len(expired),
                    branches=await self._count_branches(expired),
                    recoveries=len(expired_recoveries),
                )
            else:
                branches = 0
                for row in expired:
                    branches += await self._branches.delete_by_txn(row.global_txn_id)
                stats = CleanupStats(
                    globals=await self._txns.delete_by_ids(ConcurrentStableList(row.id for row in expired)),
                    branches=branches,
                    recoveries=await self._recoveries.delete_by_ids(
                        ConcurrentStableList(row.id for row in expired_recoveries)
                    ),
                )
        if stats.total:
            _LOGGER.info(
                "txn_ledger_cleaned",
                globals=stats.globals,
                branches=stats.branches,
                recoveries=stats.recoveries,
                retention_days=self._retention_days,
                dry_run=dry_run,
            )
            await self._report(stats)
        return stats

    async def _count_branches(self, expired: ConcurrentStableList[GlobalTxn]) -> int:
        """统计待清理事务的分支行数（`dry_run` 用；不删除）。

        Args:
            expired: 可清理事务清单。

        Returns:
            int: 分支行数合计。
        """
        total = 0
        for row in expired:
            total += len(await self._branches.list_by_txn(row.global_txn_id))
        return total

    async def _report(self, stats: CleanupStats) -> None:
        """上报清理计数（metrics 缺省时空操作）。

        Args:
            stats: 本轮统计。
        """
        metrics = self._metrics
        if metrics is None:
            return
        for scope, value in (
            ("global", stats.globals),
            ("branch", stats.branches),
            ("recovery", stats.recoveries),
        ):
            if value:
                await metrics.counter(METRIC_CLEANED, value=float(value), labels={"scope": scope})
