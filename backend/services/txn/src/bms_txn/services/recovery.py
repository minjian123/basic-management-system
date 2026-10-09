"""TM 恢复器：非终态事务对账 + **领导者选举**（仅 leader 驱动，详设 05_07 §8 第 3 项）。

- **决定点前**（未落 `committing`，含 `active` / `preparing` / `rolling_back`）：驱动全部分支回滚；
- **决定点后**（已落 `committing`）：驱动全部分支提交（**只提交、不再回滚**）；
- 到期未提交的 `active` 事务（全部分支就绪但调用方不再提交）⇒ 置回滚；
- **恢复器单飞**：多副本下经分布式锁 `bms:global:lock:txn:leader` 选举 leader，仅 leader 执行扫描；
  切换期重复驱动**由分支状态机幂等吸收**（已确认分支跳过）；
- 每次处置落 `global_txn_recovery` 台账（**只驱动协议、禁止改业务数据**）。
"""

from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.lock.base import BaseDistributedLock
from bms_core.transaction.base import TXN_COMMITTING, TXN_TERMINAL_STATES
from bms_txn.models.ledger import GlobalTxn
from bms_txn.repositories.ledger import (
    GlobalTxnBranchRepository,
    GlobalTxnRecoveryRepository,
    GlobalTxnRepository,
)
from bms_txn.services.coordinator import TransactionCoordinator

__all__ = ["TransactionRecovery"]

ACTOR_RECOVERER = "recoverer"
"""台账处置方：恢复器自动驱动。"""


class TransactionRecovery(BaseFrameworkObject):
    """全局事务恢复 / 对账器（仅 leader 驱动）。"""

    def __init__(
        self,
        coordinator: TransactionCoordinator,
        txns: GlobalTxnRepository,
        branches: GlobalTxnBranchRepository,
        recoveries: GlobalTxnRecoveryRepository,
        uow: UnitOfWork,
        lock: BaseDistributedLock,
        *,
        leader_lock_key: str,
        leader_lock_ttl: int = 30,
        batch_limit: int = 200,
    ) -> None:
        """初始化。

        Args:
            coordinator: 协调器（决定点驱动的唯一入口）。
            txns: 全局事务仓储。
            branches: 分支仓储。
            recoveries: 恢复 / 对账台账仓储。
            uow: 工作单元（**平台库**写会话）。
            lock: 分布式锁（领导者选举；复用 `[distributed_lock]`）。
            leader_lock_key: leader 锁键（缺省取 `[transaction_manager].leader_lock_key`）。
            leader_lock_ttl: leader 锁 TTL（秒）。
            batch_limit: 单轮扫描上限。
        """
        self._coordinator = coordinator
        self._txns = txns
        self._branches = branches
        self._recoveries = recoveries
        self._uow = uow
        self._lock = lock
        self._leader_lock_key = leader_lock_key
        self._leader_lock_ttl = leader_lock_ttl
        self._batch_limit = batch_limit

    async def is_leader(self) -> bool:
        """尝试取得 leader 锁（**不等待**）；取到即本副本成为 leader。

        Returns:
            bool: 是否取得 leader 身份。
        """
        token = await self._lock.acquire(self._leader_lock_key, ttl=self._leader_lock_ttl, wait=0)
        return token is not None

    async def run_once(self, *, now: datetime | None = None) -> int:
        """单轮对账：扫描非终态事务并按**决定点**驱动至终态。

        Args:
            now: 当前时间（UTC；缺省取系统时钟；用例可注入）。

        Returns:
            int: 本轮处置的事务数。
        """
        moment = now if now is not None else datetime.now(UTC)
        handled = 0
        for txn in await self._unsettled():
            if txn.state == TXN_COMMITTING:
                await self._coordinator.commit(txn.global_txn_id)
                await self._record(txn.global_txn_id, None, "drive_commit", moment)
            elif txn.deadline_at <= moment and txn.state in ("active", "preparing"):
                # 到期仍未提交 ⇒ 置回滚（详设 §6）
                await self._coordinator.rollback(txn.global_txn_id)
                await self._record(txn.global_txn_id, None, "drive_rollback", moment)
            elif txn.state in ("active", "preparing", "rolling_back"):
                await self._coordinator.rollback(txn.global_txn_id)
                await self._record(txn.global_txn_id, None, "drive_rollback", moment)
            else:
                continue
            handled += 1
        return handled

    async def run_as_leader(self, *, now: datetime | None = None) -> int:
        """以 leader 身份执行单轮对账（未取得 leader 身份时跳过）。

        Args:
            now: 当前时间（UTC）。

        Returns:
            int: 本轮处置的事务数（非 leader 为 0）。
        """
        if not await self.is_leader():
            return 0
        return await self.run_once(now=now)

    async def _unsettled(self) -> ConcurrentStableList[GlobalTxn]:
        """读非终态事务（独立只读事务）。

        Returns:
            ConcurrentStableList[GlobalTxn]: 非终态事务清单。
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
