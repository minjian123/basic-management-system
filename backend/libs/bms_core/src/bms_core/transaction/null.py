"""transaction 能力域缺省实现（Null Object）：未启用强一致，**明确拒绝**而非静默降级。

`[transaction_manager].provider` 缺省为 `null`：

- `NullTransactionManager`：`enabled=False`——调用方据此**回退既有基线路径**（本地事务 + 幂等 +
  一致性屏障），不发起全局事务；
- `NullTransactionParticipant`：协议动作一律抛 `TransactionUnavailableError`（`10013` / 503）——
  参与端点**不静默放行半套状态**（详设 05_07 §6 硬口径）；`recover_branches` 返回空元组
  （未启用两阶段 ⇒ 本库不存在悬挂分支）。
"""

from bms_core.core.capability import BaseNullObject
from bms_core.core.exceptions import TransactionUnavailableError
from bms_core.transaction.base import (
    BaseTransactionManager,
    BaseTransactionParticipant,
    BranchOp,
    BranchSpec,
    GlobalTransaction,
)

__all__ = [
    "NullTransactionManager",
    "NullTransactionParticipant",
]

UNAVAILABLE_MESSAGE = "跨服务强一致未启用（[transaction_manager].provider=null）"
"""缺省实现统一拒绝文案。"""


class NullTransactionManager(BaseTransactionManager, BaseNullObject):
    """占位事务管理器：不启用全局事务（调用方据 `enabled` 为假回退基线路径）。"""

    @property
    def enabled(self) -> bool:
        """恒定假（未启用强一致）。"""
        return False

    async def begin(
        self, *, caller_service: str, branches: tuple[BranchSpec, ...], timeout_seconds: float | None = None
    ) -> GlobalTransaction:
        """拒绝开启全局事务（未启用强一致）。

        Args:
            caller_service: 发起方服务键（占位忽略）。
            branches: 分支声明清单（占位忽略）。
            timeout_seconds: 全局提交截止（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """拒绝提交（未启用强一致）。

        Args:
            global_txn_id: 全局事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """拒绝回滚（未启用强一致）。

        Args:
            global_txn_id: 全局事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def status(self, global_txn_id: str) -> GlobalTransaction:
        """拒绝查询状态（未启用强一致）。

        Args:
            global_txn_id: 全局事务标识（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)


class NullTransactionParticipant(BaseTransactionParticipant, BaseNullObject):
    """占位参与方：协议动作明确拒绝；悬挂列举恒为空（本库无两阶段分支）。"""

    @property
    def enabled(self) -> bool:
        """恒定假（不具备两阶段能力）。"""
        return False

    async def execute_branch(self, *, xid: str, db_key: str, ops: tuple[BranchOp, ...]) -> str:
        """拒绝执行分支（未启用强一致）。

        Args:
            xid: 分支事务标识（占位忽略）。
            db_key: 目标库键（占位忽略）。
            ops: 分支操作清单（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def commit_branch(self, *, xid: str, db_key: str) -> str:
        """拒绝提交分支（未启用强一致）。

        Args:
            xid: 分支事务标识（占位忽略）。
            db_key: 目标库键（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def rollback_branch(self, *, xid: str, db_key: str) -> str:
        """拒绝回滚分支（未启用强一致）。

        Args:
            xid: 分支事务标识（占位忽略）。
            db_key: 目标库键（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def branch_state(self, *, xid: str, db_key: str) -> str:
        """拒绝查询分支状态（未启用强一致）。

        Args:
            xid: 分支事务标识（占位忽略）。
            db_key: 目标库键（占位忽略）。

        Raises:
            TransactionUnavailableError: 恒定抛出（`10013` / 503）。
        """
        raise TransactionUnavailableError(UNAVAILABLE_MESSAGE)

    async def recover_branches(self, *, db_key: str) -> tuple[str, ...]:
        """恒返回空（未启用两阶段 ⇒ 本库不存在悬挂分支）。

        Args:
            db_key: 目标库键（占位忽略）。

        Returns:
            tuple[str, ...]: 空元组。
        """
        return ()
