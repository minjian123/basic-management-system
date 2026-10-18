"""TM 恢复器：非终态事务对账 + **按决定点驱动至终态**（详设 05_07 §3.4）。

- **决定点前**（未落 `committing`，含 `active` / `preparing` / `rolling_back`）：驱动全部分支回滚；
- **决定点后**（已落 `committing`）：驱动全部分支提交（**只提交、不再回滚**）；
- 到期未提交的 `active` 事务（全部分支就绪但调用方不再提交）⇒ 置回滚（详设 §6）；
- 每次处置落 `txn_global_recovery` 台账（**只驱动协议、禁止改业务数据**）。

**职责边界**：本类只做「一轮对账逻辑」（给定一次账本会话）**不做**领导者选举与周期调度——
选举（锁 token 续租）、周期、启动期扫描与逐轮作用域构造归运行期装配
（`bms_txn.services.recovery_poll.PollTransactionRecovery`，详设 §3.4）。
"""

from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.metrics.base import BaseMetrics
from bms_core.transaction.base import TXN_ACTIVE, TXN_COMMITTING, TXN_PREPARING, TXN_ROLLING_BACK, TXN_TERMINAL_STATES
from bms_txn.models.ledger import GlobalTxn
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.services.coordinator import TransactionCoordinator

__all__ = [
    "ACTION_DRIVE_COMMIT",
    "ACTION_DRIVE_ROLLBACK",
    "ACTOR_RECOVERER",
    "DEFAULT_BATCH_LIMIT",
    "METRIC_HUNG",
    "METRIC_RECOVERY",
    "TransactionRecovery",
]

ACTOR_RECOVERER = "recoverer"
"""台账处置方：恢复器自动驱动。"""

ACTION_DRIVE_COMMIT = "drive_commit"
"""处置动作：按决定点驱动提交。"""

ACTION_DRIVE_ROLLBACK = "drive_rollback"
"""处置动作：决定点前驱动回滚（含到期未提交）。"""

DEFAULT_BATCH_LIMIT = 200
"""单轮扫描上限（缺省）。"""

METRIC_RECOVERY = "bms_txn_recovery_total"
"""指标：恢复驱动次数（按动作）。"""

METRIC_HUNG = "bms_txn_hung"
"""指标：悬挂（非终态）全局事务数。"""


class TransactionRecovery(BaseFrameworkObject):
    """全局事务恢复 / 对账器（单轮逻辑；领导者选举与周期调度见 `recovery_poll`）。"""

    def __init__(
        self,
        coordinator: TransactionCoordinator,
        txns: GlobalTxnRepository,
        branches: GlobalTxnBranchRepository,
        recoveries: GlobalTxnRecoveryRepository,
        uow: UnitOfWork,
        *,
        batch_limit: int = DEFAULT_BATCH_LIMIT,
        metrics: BaseMetrics | None = None,
    ) -> None:
        """初始化。

        Args:
            coordinator: 协调器（决定点驱动的唯一入口）。
            txns: 全局事务仓储。
            branches: 分支仓储。
            recoveries: 恢复 / 对账台账仓储。
            uow: 工作单元（**平台库**写会话）。
            batch_limit: 单轮扫描上限。
            metrics: 指标出口（None 不上报；见《详设 05_07》§3.4）。
        """
        self._coordinator = coordinator
        self._txns = txns
        self._branches = branches
        self._recoveries = recoveries
        self._uow = uow
        self._batch_limit = batch_limit
        self._metrics = metrics

    async def run_once(self, *, now: datetime | None = None) -> int:
        """单轮对账：扫描非终态事务并按**决定点**驱动至终态。

        Args:
            now: 当前时间（UTC；缺省取系统时钟；用例可注入）。

        Returns:
            int: 本轮处置的事务数。
        """
        moment = now if now is not None else datetime.now(UTC)
        unsettled = await self._unsettled()
        await self._report_hung(len(unsettled))
        handled = 0
        for txn in unsettled:
            action = _action_for(txn)
            if action is None:
                continue
            if action == ACTION_DRIVE_COMMIT:
                await self._coordinator.commit(txn.global_txn_id)
            else:
                await self._coordinator.rollback(txn.global_txn_id)
            await self._record(txn.global_txn_id, None, action, moment)
            await self._count(action)
            handled += 1
        return handled

    async def _unsettled(self) -> ConcurrentStableList[GlobalTxn]:
        """读非终态事务（独立只读事务）。

        Returns:
            ConcurrentStableList[GlobalTxn]: 非终态事务清单（已按状态二次过滤）。
        """
        result: ConcurrentStableList[GlobalTxn] = ConcurrentStableList()
        async with self._uow.begin():
            rows = await self._txns.list_unsettled(limit=self._batch_limit)
            for row in rows:
                if row.state not in TXN_TERMINAL_STATES:
                    result.add(row)
        return result

    async def _record(self, global_txn_id: str, branch_id: str | None, action: str, moment: datetime) -> None:
        """落恢复 / 对账台账（处置动作**只驱动协议**）。

        Args:
            global_txn_id: 全局事务标识。
            branch_id: 分支标识（整事务级为 None）。
            action: 处置动作（`drive_commit` / `drive_rollback`）。
            moment: 发现时刻（UTC）。
        """
        async with self._uow.begin():
            state = None
            txn = await self._txns.get_by_global_txn_id(global_txn_id)
            if txn is not None:
                state = txn.state
            conclusion = f"驱动后状态={state}" if state is not None else "事务记录缺失"
            await self._recoveries.create(
                global_txn_id=global_txn_id,
                branch_id=branch_id,
                detected_at=moment,
                hung_seconds=None,
                action=action,
                actor=ACTOR_RECOVERER,
                handler=None,
                conclusion=conclusion[:255],
            )

    async def _count(self, action: str) -> None:
        """上报一次恢复驱动（metrics 缺省时空操作）。

        Args:
            action: 处置动作（`drive_commit` / `drive_rollback`）。
        """
        metrics = self._metrics
        if metrics is None:
            return
        await metrics.counter(METRIC_RECOVERY, labels={"action": action})

    async def _report_hung(self, value: int) -> None:
        """上报悬挂（非终态）事务数（metrics 缺省时空操作）。

        Args:
            value: 本轮扫描到的非终态事务数。
        """
        metrics = self._metrics
        if metrics is None:
            return
        await metrics.gauge(METRIC_HUNG, value=float(value))


def _action_for(txn: GlobalTxn) -> str | None:
    """按**决定点**与状态决定处置动作（None = 非本轮处置对象）。

    Args:
        txn: 全局事务行。

    Returns:
        str | None: `drive_commit`（决定点后）/ `drive_rollback`（决定点前）/ None（非在途状态）。
    """
    if txn.state == TXN_COMMITTING:
        return ACTION_DRIVE_COMMIT
    if txn.state in (TXN_ACTIVE, TXN_PREPARING, TXN_ROLLING_BACK):
        return ACTION_DRIVE_ROLLBACK
    return None
