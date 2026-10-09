"""跨服务事务能力域契约：TM 调用方门面 + 参与方分支执行（强一致专项 05_07）。

口径（详设 05_07 §3.3 / §5）：

- **TM 是纯跨库协调基础设施**——与租户、与业务无关；分支目标库以**不透明库键**（`db_key`）表达。
- **分支执行＝一次请求**：单请求内 `XA_START → 业务写 → XA_END → XA_PREPARE`，连接随请求释放。
- **提交决定点唯一权威**：TM 落 `committing` 之前一切失败一律回滚，之后只 `commit`、不再回滚。
- **两阶段仅同步引擎可用**（SQLAlchemy 异步 API 不暴露 `begin_twophase`）：分支走分支专用同步引擎。
- **缺省 `null`**：`provider=null` 时管理器不启全局事务（回退既有基线）、参与方端点明确拒绝（不静默降级）。

本模块只定义**契约**；实现见 `bms_core.transaction.null` / `bms_core.transaction.xa`。
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from fastapi import Request

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable, resolve_plugin
from bms_core.db.session import DbSession

TRANSACTION_MANAGER_KEY = "transaction_manager"
"""能力域键：跨服务事务管理器（调用方门面）。"""

TRANSACTION_PARTICIPANT_KEY = "transaction_participant"

TM_SERVICE_NAME = "txn"
"""TM 服务键（账本与协调器所在服务；参与端点 `commit` / `rollback` / 状态查询仅接受该服务身份）。"""
"""能力域键：跨服务事务参与方（分支执行）。"""

TXN_ACTIVE = "active"
"""全局事务：已开启、分支执行中。"""

TXN_PREPARING = "preparing"
"""全局事务：调用方已请求提交、TM 正在核验分支。"""

TXN_COMMITTING = "committing"
"""全局事务：**提交决定点**（此后续行只提交）。"""

TXN_COMMITTED = "committed"
"""全局事务：全部分支已提交（终态）。"""

TXN_ROLLING_BACK = "rolling_back"
"""全局事务：决定点前失败 / 调用方放弃 / 截止到期，正在回滚。"""

TXN_ROLLED_BACK = "rolled_back"
"""全局事务：全部分支已回滚（终态）。"""

TXN_HEURISTIC_COMMIT = "heuristic_commit"
"""异常终态：参与方单方面提交（启发式完成）。"""

TXN_HEURISTIC_ROLLBACK = "heuristic_rollback"
"""异常终态：参与方单方面回滚（启发式完成）。"""

TXN_HEURISTIC_MIXED = "heuristic_mixed"
"""异常终态：部分提交、部分回滚（启发式混合，须对账处置）。"""

TXN_STATES: tuple[str, ...] = (
    TXN_ACTIVE,
    TXN_PREPARING,
    TXN_COMMITTING,
    TXN_COMMITTED,
    TXN_ROLLING_BACK,
    TXN_ROLLED_BACK,
    TXN_HEURISTIC_COMMIT,
    TXN_HEURISTIC_ROLLBACK,
    TXN_HEURISTIC_MIXED,
)
"""全局事务状态取值全集（登记用）。"""

TXN_TERMINAL_STATES: tuple[str, ...] = (
    TXN_COMMITTED,
    TXN_ROLLED_BACK,
    TXN_HEURISTIC_COMMIT,
    TXN_HEURISTIC_ROLLBACK,
    TXN_HEURISTIC_MIXED,
)
"""全局事务终态集合（非终态 = 在途，恢复器扫描对象）。"""

BRANCH_ACTIVE = "active"
"""分支：已开启、未准备。"""

BRANCH_PREPARED = "prepared"
"""分支：已 `XA_PREPARE`（业务仍不可见）。"""

BRANCH_COMMITTED = "committed"
"""分支：已提交。"""

BRANCH_ROLLED_BACK = "rolled_back"
"""分支：已回滚。"""

BRANCH_REJECTED = "rejected"
"""分支：准备阶段否决（TM 据此回滚全部分支）。"""

BRANCH_STATES: tuple[str, ...] = (BRANCH_ACTIVE, BRANCH_PREPARED, BRANCH_COMMITTED, BRANCH_ROLLED_BACK, BRANCH_REJECTED)
"""分支状态取值全集。"""


XA_XID_SEPARATOR = "|"
"""XA `xid` 内部分隔符（`gtrid|bqual`）。"""

MAX_XA_XID_BYTES = 64
"""XA `xid` 最严上限（MySQL `XA` 要求 `xid` ≤ 64 字节；三库按最严口径统一）。"""

MAX_BRANCH_ID_LENGTH = 16
"""分支标识最大长度（预留 `gtrid` 与分隔符后仍满足 `MAX_XA_XID_BYTES`）。"""


def build_branch_xid(global_txn_id: str, branch_id: str) -> str:
    """构建分支 `xid`（`gtrid|bqual` 文本形态；TM 生成、参与方原样透传）。

    形态满足三库最严约束：`gtrid = global_txn_id`、`bqual = branch_id`、
    `formatID = 1`（由方言实现承载）——总长不超过 `MAX_XA_XID_BYTES`。

    Args:
        global_txn_id: 全局事务标识。
        branch_id: 分支标识。

    Returns:
        str: 分支 `xid`。

    Raises:
        ParamError: 长度超限（`10001`）。
    """
    if len(branch_id) > MAX_BRANCH_ID_LENGTH:
        raise ParamError(f"分支标识过长（上限 {MAX_BRANCH_ID_LENGTH}）：{branch_id}")
    xid = f"{global_txn_id}{XA_XID_SEPARATOR}{branch_id}"
    if len(xid.encode("utf-8")) > MAX_XA_XID_BYTES:
        raise ParamError(f"分支 xid 超过 XA 上限（{MAX_XA_XID_BYTES} 字节）：{xid}")
    return xid


@dataclass(frozen=True)
class BranchSpec(BaseValueObject):
    """分支声明（调用方 `begin` 时给出；TM 只作寻址，不解释业务语义）。"""

    branch_id: str
    """分支标识（同一全局事务内唯一）。"""

    service: str
    """参与方服务键（分支执行端点的服务身份白名单来源）。"""

    db_key: str
    """**不透明库键**（分支目标库；平台 / 租户 / 归档库均可）。"""


@dataclass(frozen=True)
class BranchRef(BranchSpec):
    """已分配 `xid` 的分支（TM 分配后回传）。"""

    xid: str
    """XA 事务标识（由 TM 生成，满足三库最严约束）。"""

    state: str = ""
    """分支状态（`BRANCH_*`）。"""

    retry_count: int = 0
    """TM 驱动重试次数。"""


@dataclass(frozen=True)
class GlobalTransaction(BaseValueObject):
    """全局事务快照（`begin` / `commit` / `rollback` / `status` 的统一返回）。"""

    global_txn_id: str
    """全局事务标识（同时作为 XA `gtrid`）。"""

    caller_service: str
    """发起方服务键。"""

    state: str
    """全局事务状态（`TXN_*`）。"""

    deadline_at: datetime | None = None
    """提交决定截止时间（UTC）；调用方门面经远端快照构造时可能缺省。"""

    decided_at: datetime | None = None
    """提交决定点时间（UTC；非空即已过决定点）。"""

    branches: tuple[BranchRef, ...] = ()
    """分支清单（含 `xid`）。"""

    @property
    def is_terminal(self) -> bool:
        """是否处于终态。"""
        return self.state in TXN_TERMINAL_STATES


class BranchHandlerRegistry(BaseFrameworkObject):
    """分支业务处理器注册表（**统一注册通道**）。

    参与方服务的分支执行**不复制业务逻辑**：把 `op` 名映射到本服务**已有服务层方法**，
    由分支执行器在同步会话上调用（详设 §3.2「分支驱动端点只做协议执行并调用本服务已有业务方法」）。
    """

    def __init__(self) -> None:
        """初始化空注册表。"""
        self._handlers: ConcurrentStableDict[str, BranchHandler] = ConcurrentStableDict()

    def register(self, op: str, handler: BranchHandler) -> None:
        """登记分支处理器（同 `op` 重复登记即拒——防隐式覆盖）。

        Args:
            op: 操作名（分支载荷 `op` 字段取值）。
            handler: 分支业务处理器（收同步 / 异步会话与参数，执行本服务已有服务层调用）。

        Raises:
            ValueError: `op` 已登记。
        """
        if op in self._handlers:
            raise ValueError(f"分支处理器已登记：{op}")
        self._handlers.set(op, handler)

    def resolve(self, op: str) -> BranchHandler | None:
        """取分支处理器（未登记返回 `None`，由执行器拒绝该分支）。

        Args:
            op: 操作名。

        Returns:
            BranchHandler | None: 分支业务处理器。
        """
        return self._handlers.get(op)

    def ops(self) -> tuple[str, ...]:
        """已登记操作名（排障 / 用例断言用）。"""
        return tuple(self._handlers.keys())


BranchHandler = Callable[[DbSession, ConcurrentStableDict[str, object]], Awaitable[None]]
"""分支业务处理器签名：`(会话, 参数) → None`（会话为同步 / 异步联合类型）。"""


class BaseTransactionManager(BasePluggable, ABC):
    """跨服务事务管理器（**调用方门面**）：开启 / 提交 / 回滚 / 查状态。"""

    key: str = TRANSACTION_MANAGER_KEY
    plugin_key: str = TRANSACTION_MANAGER_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """是否启用强一致（`null` 提供者为假——调用方据此回退既有基线路径）。"""

    @abstractmethod
    async def begin(
        self, *, caller_service: str, branches: tuple[BranchSpec, ...], timeout_seconds: float | None = None
    ) -> GlobalTransaction:
        """开启全局事务并分配各分支 `xid`。

        Args:
            caller_service: 发起方服务键。
            branches: 分支声明清单（非空）。
            timeout_seconds: 全局提交截止（秒）；None 取配置缺省。

        Returns:
            GlobalTransaction: 全局事务快照（含各分支 `xid`）。
        """

    @abstractmethod
    async def commit(self, global_txn_id: str) -> GlobalTransaction:
        """请求提交（TM 核验全部分支 `prepared` 后落决定点并逐分支提交）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 提交后的全局事务快照。
        """

    @abstractmethod
    async def rollback(self, global_txn_id: str) -> GlobalTransaction:
        """请求回滚（决定点之前有效；之后由 TM 幂等吸收）。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 回滚后的全局事务快照。
        """

    @abstractmethod
    async def status(self, global_txn_id: str) -> GlobalTransaction:
        """查询全局事务状态。

        Args:
            global_txn_id: 全局事务标识。

        Returns:
            GlobalTransaction: 当前快照。
        """


@dataclass(frozen=True)
class BranchOp(BaseValueObject):
    """分支内的单个业务操作（`op` 映射参与方**已有服务层方法**；一个分支可含多个操作）。

    一个分支＝一条 XA 事务＝一条数据库连接，故同一分支内的多个操作**必须一次请求执行**；
    调用方可按需把同库的多个写入合并进同一分支（如「用户-岗位 + 用户-部门」）。
    """

    op: str
    """操作名（参与方分支处理器注册表键）。"""

    args: ConcurrentStableDict[str, object]
    """业务载荷（交给参与方已有服务层）。"""


class BaseTransactionParticipant(BasePluggable, ABC):
    """跨服务事务参与方（**分支执行**）：协议执行 + 本服务已有服务层调用。"""

    key: str = TRANSACTION_PARTICIPANT_KEY
    plugin_key: str = TRANSACTION_PARTICIPANT_KEY
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """是否具备两阶段能力（`null` 提供者为假——参与端点据此明确拒绝）。"""

    @abstractmethod
    async def execute_branch(self, *, xid: str, db_key: str, ops: tuple[BranchOp, ...]) -> str:
        """执行分支：`XA_START → 业务写 → XA_END → XA_PREPARE`（单请求内完成、连接随请求释放）。

        Args:
            xid: 分支事务标识（TM 分配）。
            db_key: 目标库键（不透明；参与方按本服务引擎注册表解析）。
            op: 操作名（分支处理器注册表键）。
            args: 业务载荷（交给本服务已有服务层）。

        Returns:
            str: 分支状态（`prepared` / `rejected`）。
        """

    @abstractmethod
    async def commit_branch(self, *, xid: str, db_key: str) -> str:
        """提交分支（`XA_COMMIT`；由 TM 驱动）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`committed`）。
        """

    @abstractmethod
    async def rollback_branch(self, *, xid: str, db_key: str) -> str:
        """回滚分支（`XA_ROLLBACK`；由 TM 驱动）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`rolled_back`）。
        """

    @abstractmethod
    async def branch_state(self, *, xid: str, db_key: str) -> str:
        """查询分支状态（TM 决定点前核验）。

        Args:
            xid: 分支事务标识。
            db_key: 目标库键。

        Returns:
            str: 分支状态（`BRANCH_*`）。
        """

    @abstractmethod
    async def recover_branches(self, *, db_key: str) -> tuple[str, ...]:
        """列举本库悬挂分支（`XA_RECOVER` 对账用；返回可回放的 `xid` 文本形态）。

        Args:
            db_key: 目标库键。

        Returns:
            tuple[str, ...]: 悬挂分支 `xid`（无悬挂为空元组）。
        """


def get_transaction_manager(request: Request) -> BaseTransactionManager:
    """取应用级事务管理器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTransactionManager: 应用装配的事务管理器实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTransactionManager",
        resolve_plugin(
            TRANSACTION_MANAGER_KEY,
            settings.transaction_manager.provider,
            expected_version=BaseTransactionManager.contract_version,
        ),
    )


def get_transaction_participant(request: Request) -> BaseTransactionParticipant:
    """取应用级事务参与方（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseTransactionParticipant: 应用装配的参与方实例。
    """
    settings = cast("Settings", request.app.state.settings)
    return cast(
        "BaseTransactionParticipant",
        resolve_plugin(
            TRANSACTION_PARTICIPANT_KEY,
            settings.transaction_manager.provider,
            expected_version=BaseTransactionParticipant.contract_version,
        ),
    )


__all__ = [
    "BRANCH_ACTIVE",
    "BRANCH_COMMITTED",
    "BRANCH_PREPARED",
    "BRANCH_REJECTED",
    "BRANCH_ROLLED_BACK",
    "BRANCH_STATES",
    "MAX_BRANCH_ID_LENGTH",
    "MAX_XA_XID_BYTES",
    "TM_SERVICE_NAME",
    "TRANSACTION_MANAGER_KEY",
    "TRANSACTION_PARTICIPANT_KEY",
    "TXN_ACTIVE",
    "TXN_COMMITTED",
    "TXN_COMMITTING",
    "TXN_HEURISTIC_COMMIT",
    "TXN_HEURISTIC_MIXED",
    "TXN_HEURISTIC_ROLLBACK",
    "TXN_PREPARING",
    "TXN_ROLLED_BACK",
    "TXN_ROLLING_BACK",
    "TXN_STATES",
    "TXN_TERMINAL_STATES",
    "XA_XID_SEPARATOR",
    "BaseTransactionManager",
    "BaseTransactionParticipant",
    "BranchHandler",
    "BranchHandlerRegistry",
    "BranchOp",
    "BranchRef",
    "BranchSpec",
    "GlobalTransaction",
    "build_branch_xid",
    "get_transaction_manager",
    "get_transaction_participant",
]
