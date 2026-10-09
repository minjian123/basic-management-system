"""TM 协调器：全局事务状态机 + **提交决定点唯一权威** + 分支驱动与幂等（详设 05_07 §3）。

关键不变量（§3.1）：

- 账本落 `committing` 的那一刻即**提交决定点**：**此之前一切失败一律回滚，之后只提交、不再回滚**；
- 每条驱动消息带 `global_txn_id` + `branch_id`，重复驱动**由分支状态机幂等吸收**；
- 准备阶段超时按失败处理；决定点之后不超时回滚（靠恢复器重驱动）；
- 账本写走**行级乐观锁**（`BaseModel.version`），并发冲突即重试。

**去租户**：TM 不感知租户 / 业务；分支目标库以 `db_key` 不透明透传。
"""

from datetime import UTC, datetime, timedelta

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.core.id import id_generator
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.transaction.base import (
    BRANCH_ACTIVE,
    BRANCH_COMMITTED,
    BRANCH_PREPARED,
    BRANCH_REJECTED,
    BRANCH_ROLLED_BACK,
    TXN_ACTIVE,
    TXN_COMMITTED,
    TXN_COMMITTING,
    TXN_PREPARING,
    TXN_ROLLED_BACK,
    TXN_ROLLING_BACK,
    TXN_TERMINAL_STATES,
    BranchRef,
    BranchSpec,
    GlobalTransaction,
    build_branch_xid,
)
from bms_txn.models.ledger import GlobalTxn, GlobalTxnBranch
from bms_txn.repositories.ledger import GlobalTxnBranchRepository, GlobalTxnRepository
from bms_txn.services.driver import BranchDriver

__all__ = ["TransactionCoordinator"]

DEFAULT_DEADLINE_SECONDS = 300.0
"""缺省全局提交截止（秒）。"""


class TransactionCoordinator(BaseFrameworkObject):
    """全局事务协调器（TM 核心）。"""

    def __init__(
        self,
        txns: GlobalTxnRepository,
        branches: GlobalTxnBranchRepository,
        uow: UnitOfWork,
        driver: BranchDriver,
        *,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ) -> None:
        """初始化。

        Args:
            txns: 全局事务主记录仓储（`bms_txn` 平台库）。
            branches: 分支仓储。
            uow: 工作单元（**平台库**写会话）。
            driver: 分支驱动端口（真实实现见参与端点接入）。
            deadline_seconds: 全局提交截止（秒；`begin` 未显式指定时取用）。
        """
        self._txns = txns
        self._branches = branches
        self._uow = uow
        self._driver = driver
        self._deadline_seconds = deadline_seconds

    async def begin(
        self, *, caller_service: str, branches: tuple[BranchSpec, ...], timeout_seconds: float | None = None
    ) -> GlobalTransaction:
        """开启全局事务并分配各分支 `xid`。

        Args:
            caller_service: 发起方服务键（取自服务身份）。
            branches: 分支声明清单（非空、`branch_id` 唯一）。
            timeout_seconds: 全局提交截止（秒）；None 取配置缺省。

        Returns:
            GlobalTransaction: 含各分支 `xid` 的全局事务快照。

        Raises:
            ParamError: 分支清单为空 / `branch_id` 重复 / `xid` 超长（`10001`）。
        """
        self._validate_branches(branches)
        deadline_seconds = timeout_seconds if timeout_seconds is not None else self._deadline_seconds
        now = datetime.now(UTC)
        global_txn_id = str(id_generator.next_id())
        async with self._uow.begin():
            txn = await self._txns.create(
                global_txn_id=global_txn_id,
                caller_service=caller_service,
                state=TXN_ACTIVE,
                deadline_at=now + timedelta(seconds=deadline_seconds),
                decided_at=None,
            )
            rows = ConcurrentStableList[GlobalTxnBranch]()
            for spec in branches:
                rows.add(
                    await self._branches.create(
                        global_txn_id=global_txn_id,
                        branch_id=spec.branch_id,
                        service=spec.service,
                        db_key=spec.db_key,
                        xid=build_branch_xid(global_txn_id, spec.branch_id),
                        state=BRANCH_ACTIVE,
                    )
                )
            snapshot = self._snapshot(txn, rows)
        return snapshot

    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """请求提交：核验分支 → 落决定点 → 逐分支提交（幂等可重入）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 提交后的全局事务快照。

        Raises:
            TransactionNotFoundError: 事务不存在（`10013` 同域口径之外的 404 语义由 `ParamError` 表达）。
            TransactionConflictError: 并发写账本冲突（可重试）。
        """
        state = await self._prepare(global_txn_id)
        if state in TXN_TERMINAL_STATES:
            return await self.status(global_txn_id)
        if state == TXN_COMMITTING:
            await self._drive(global_txn_id, commit=True)
            return await self.status(global_txn_id)

        # 核验分支状态（决定点前）：全票 `prepared` 才提交，否则回滚全部分支
        branch_rows = await self._read_branches(global_txn_id)
        all_prepared = len(branch_rows) > 0
        for row in branch_rows:
            try:
                observed = await self._driver.verify(service=row.service, db_key=row.db_key, xid=row.xid)
            except Exception as error:  # 任一分支核验失败即按否决处理（回滚）
                observed = BRANCH_REJECTED
                await self._record_branch_error(global_txn_id, row.branch_id, str(error))
            if observed == BRANCH_PREPARED:
                await self._set_branch_state(global_txn_id, row.branch_id, BRANCH_PREPARED)
            else:
                all_prepared = False

        if all_prepared:
            await self._decide(global_txn_id, TXN_COMMITTING)
            await self._drive(global_txn_id, commit=True)
        else:
            await self._decide(global_txn_id, TXN_ROLLING_BACK)
            await self._drive(global_txn_id, commit=False)
        return await self.status(global_txn_id)

    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """请求回滚（**决定点之前有效**；之后由 TM 幂等吸收、不回滚）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 回滚后的全局事务快照。
        """
        state = await self._prepare(global_txn_id)
        if state in TXN_TERMINAL_STATES:
            return await self.status(global_txn_id)
        if state == TXN_COMMITTING:
            # 已过决定点：**只提交、不再回滚**（幂等吸收）
            await self._drive(global_txn_id, commit=True)
            return await self.status(global_txn_id)
        await self._decide(global_txn_id, TXN_ROLLING_BACK)
        await self._drive(global_txn_id, commit=False)
        return await self.status(global_txn_id)

    async def status(self, global_txn_id: str) -> GlobalTransaction:
        """查询全局事务状态。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 当前快照。

        Raises:
            ParamError: 事务不存在（`10001`）。
        """
        async with self._uow.begin():
            txn = await self._txns.get_by_global_txn_id(global_txn_id)
            if txn is None:
                raise ParamError(f"全局事务不存在：{global_txn_id}")
            rows = await self._branches.list_by_txn(global_txn_id)
            return self._snapshot(txn, rows)

    async def _prepare(self, global_txn_id: str) -> str:
        """进入准备阶段（`active` → `preparing`）并返回当前状态。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            str: 当前状态（调用方据状态分流）。

        Raises:
            ParamError: 事务不存在（`10001`）。
        """
        async with self._uow.begin():
            txn = await self._txns.get_by_global_txn_id(global_txn_id)
            if txn is None:
                raise ParamError(f"全局事务不存在：{global_txn_id}")
            if txn.state == TXN_ACTIVE:
                txn.state = TXN_PREPARING
                await self._txns.flush()
            return txn.state

    async def _decide(self, global_txn_id: str, state: str) -> None:
        """落**提交决定点**（`committing`）或回滚态（决定点前）。

        Args:
            global_txn_id: 全局事务标识。
            state: 目标状态（`committing` / `rolling_back`）。
        """
        async with self._uow.begin():
            txn = await self._txns.get_by_global_txn_id(global_txn_id)
            if txn is None:
                raise ParamError(f"全局事务不存在：{global_txn_id}")
            if txn.state in TXN_TERMINAL_STATES:
                return
            txn.state = state
            if state == TXN_COMMITTING and txn.decided_at is None:
                txn.decided_at = datetime.now(UTC)
            await self._txns.flush()

    async def _read_branches(self, global_txn_id: str) -> ConcurrentStableList[GlobalTxnBranch]:
        """读分支清单（独立只读事务）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            ConcurrentStableList[GlobalTxnBranch]: 分支清单。
        """
        async with self._uow.begin():
            return await self._branches.list_by_txn(global_txn_id)

    async def _set_branch_state(self, global_txn_id: str, branch_id: str, state: str) -> None:
        """置单个分支状态。

        Args:
            global_txn_id: 全局事务标识。
            branch_id: 分支标识。
            state: 目标状态。
        """
        async with self._uow.begin():
            row = await self._branches.get_branch(global_txn_id, branch_id)
            if row is None:
                return
            if row.state == state:
                return
            row.state = state
            await self._branches.flush()

    async def _record_branch_error(self, global_txn_id: str, branch_id: str, message: str) -> None:
        """记录分支驱动失败原因与重试次数（截断落库）。

        Args:
            global_txn_id: 全局事务标识。
            branch_id: 分支标识。
            message: 失败原因。
        """
        async with self._uow.begin():
            row = await self._branches.get_branch(global_txn_id, branch_id)
            if row is None:
                return
            row.retry_count = row.retry_count + 1
            row.last_error = message[:512]
            await self._branches.flush()

    async def _drive(self, global_txn_id: str, *, commit: bool) -> None:
        """驱动全部分支到指定终态（幂等：已确认分支跳过）。

        Args:
            global_txn_id: 全局事务标识。
            commit: True 提交 / False 回滚。
        """
        rows = await self._read_branches(global_txn_id)
        expected = BRANCH_COMMITTED if commit else BRANCH_ROLLED_BACK
        for row in rows:
            if row.state == expected:
                continue
            try:
                if commit:
                    await self._driver.commit(service=row.service, db_key=row.db_key, xid=row.xid)
                else:
                    await self._driver.rollback(service=row.service, db_key=row.db_key, xid=row.xid)
            except Exception as error:
                await self._record_branch_error(global_txn_id, row.branch_id, str(error))
                continue
            await self._set_branch_state(global_txn_id, row.branch_id, expected)
        final = TXN_COMMITTED if commit else TXN_ROLLED_BACK
        await self._decide(global_txn_id, final)

    @staticmethod
    def _validate_branches(branches: tuple[BranchSpec, ...]) -> None:
        """校验分支声明（非空 / `branch_id` 唯一 / `xid` 长度可承载）。

        Args:
            branches: 分支声明清单。

        Raises:
            ParamError: 分支为空 / `branch_id` 重复（`10001`）。
        """
        if not branches:
            raise ParamError("全局事务至少需要一个分支")
        seen = ConcurrentStableDict[str, int]()
        for spec in branches:
            if spec.branch_id in seen:
                raise ParamError(f"分支标识重复：{spec.branch_id}")
            seen.set(spec.branch_id, 1)
            # 长度约束在 `build_branch_xid` 内统一校验（三库最严 = MySQL `XA` xid ≤ 64 字节）
            build_branch_xid("0" * 19, spec.branch_id)

    @staticmethod
    def _snapshot(txn: GlobalTxn, rows: ConcurrentStableList[GlobalTxnBranch]) -> GlobalTransaction:
        """ORM 行 → 契约快照。

        Args:
            txn: 事务行。
            rows: 分支行清单。

        Returns:
            GlobalTransaction: 契约快照。
        """
        refs: ConcurrentStableList[BranchRef] = ConcurrentStableList()
        for row in rows:
            refs.add(
                BranchRef(
                    branch_id=row.branch_id,
                    service=row.service,
                    db_key=row.db_key,
                    xid=row.xid,
                    state=row.state,
                    retry_count=row.retry_count,
                )
            )
        return GlobalTransaction(
            global_txn_id=txn.global_txn_id,
            caller_service=txn.caller_service,
            state=txn.state,
            deadline_at=txn.deadline_at,
            decided_at=txn.decided_at,
            branches=tuple(refs),
        )
