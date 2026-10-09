"""跨服务事务账本仓储（平台库 `bms_txn`）。

仓储只做数据访问（查询 / 落库），业务规则归 `bms_txn.services`。
"""

from datetime import datetime

from sqlalchemy import Select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_txn.models.ledger import GlobalTxn, GlobalTxnBranch, GlobalTxnRecovery

__all__ = ["GlobalTxnBranchRepository", "GlobalTxnRecoveryRepository", "GlobalTxnRepository"]


class GlobalTxnRepository(BaseDbRepository[GlobalTxn]):
    """全局事务主记录仓储（`global_txn`）。"""

    model = GlobalTxn
    sortable_fields = ConcurrentStableSet({"id", "state", "created_at", "deadline_at"})

    async def flush(self) -> None:
        """落库当前会话变更（服务层在同一事务内直接改 ORM 属性后调用）。"""
        await self._session.flush()

    async def get_by_global_txn_id(self, global_txn_id: str) -> GlobalTxn | None:
        """按全局事务标识取记录（不含软删除）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTxn | None: 事务记录；不存在返回 None。
        """
        statement = self._select().where(self._column("global_txn_id") == global_txn_id)
        return (await self._session.execute(statement)).scalars().first()

    async def list_unsettled(self, *, limit: int = 200) -> ConcurrentStableList[GlobalTxn]:
        """取非终态全局事务（恢复器扫描对象；按截止时间升序）。

        Args:
            limit: 单轮上限。

        Returns:
            ConcurrentStableList[GlobalTxn]: 非终态事务清单。
        """
        statement: Select[tuple[GlobalTxn]] = (
            self._select()
            .where(
                self._column("state").not_in(
                    ("committed", "rolled_back", "heuristic_commit", "heuristic_rollback", "heuristic_mixed")
                )
            )
            .order_by(self._column("deadline_at").asc(), self._column("id").asc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_heuristic(self, *, limit: int = 200) -> ConcurrentStableList[GlobalTxn]:
        """取启发式完成事务（参与方单方面提交 / 回滚形成的异常终态；对账对象）。

        Args:
            limit: 单轮上限。

        Returns:
            ConcurrentStableList[GlobalTxn]: 启发式终态事务清单。
        """
        statement = (
            self._select()
            .where(self._column("state").in_(("heuristic_commit", "heuristic_rollback", "heuristic_mixed")))
            .order_by(self._column("id").asc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_expired_active(self, *, now: datetime, limit: int = 200) -> ConcurrentStableList[GlobalTxn]:
        """取**已过截止**的 `active` 事务（全部分支就绪但调用方不再提交 ⇒ 置回滚）。

        Args:
            now: 当前时间（UTC）。
            limit: 单轮上限。

        Returns:
            ConcurrentStableList[GlobalTxn]: 到期未提交事务清单。
        """
        statement = (
            self._select()
            .where(self._column("state") == "active")
            .where(self._column("deadline_at") <= now)
            .order_by(self._column("id").asc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())


class GlobalTxnBranchRepository(BaseDbRepository[GlobalTxnBranch]):
    """分支仓储（`global_txn_branch`）。"""

    model = GlobalTxnBranch
    sortable_fields = ConcurrentStableSet({"id", "state", "created_at"})

    async def flush(self) -> None:
        """落库当前会话变更。"""
        await self._session.flush()

    async def list_by_txn(self, global_txn_id: str) -> ConcurrentStableList[GlobalTxnBranch]:
        """取某全局事务的全部分支（按主键升序，稳定顺序）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            ConcurrentStableList[GlobalTxnBranch]: 分支清单。
        """
        statement = (
            self._select().where(self._column("global_txn_id") == global_txn_id).order_by(self._column("id").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_branch(self, global_txn_id: str, branch_id: str) -> GlobalTxnBranch | None:
        """取单个分支。

        Args:
            global_txn_id: 全局事务标识。
            branch_id: 分支标识。

        Returns:
            GlobalTxnBranch | None: 分支记录；不存在返回 None。
        """
        statement = (
            self._select()
            .where(self._column("global_txn_id") == global_txn_id)
            .where(self._column("branch_id") == branch_id)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def list_unsettled(self, *, limit: int = 500) -> ConcurrentStableList[GlobalTxnBranch]:
        """取未确认分支（`active` / `prepared`；恢复器对账用）。

        Args:
            limit: 单轮上限。

        Returns:
            ConcurrentStableList[GlobalTxnBranch]: 未确认分支清单。
        """
        statement = (
            self._select()
            .where(self._column("state").in_(("active", "prepared")))
            .order_by(self._column("id").asc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())


class GlobalTxnRecoveryRepository(BaseDbRepository[GlobalTxnRecovery]):
    """恢复 / 对账台账仓储（`global_txn_recovery`）。"""

    model = GlobalTxnRecovery
    sortable_fields = ConcurrentStableSet({"id", "detected_at"})

    async def flush(self) -> None:
        """落库当前会话变更。"""
        await self._session.flush()

    async def list_recent(self, *, limit: int = 100) -> ConcurrentStableList[GlobalTxnRecovery]:
        """取最近处置记录（按发现时刻倒序）。

        Args:
            limit: 上限。

        Returns:
            ConcurrentStableList[GlobalTxnRecovery]: 处置记录清单。
        """
        statement = self._select().order_by(self._column("id").desc()).limit(limit)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())
