"""参与端点路由器工厂：`/api/v1/txn/branches*`（**谁挂端点谁参与**，强一致专项 05_07）。

参与方服务在 `service_routers()` 中挂载 `build_branch_router()` 即成为**可远程驱动的参与方**：

| 端点 | 鉴权 | 语义 |
| --- | --- | --- |
| `POST /api/v1/txn/branches` | 服务身份（发起方执行远端分支） | 分支执行：`XA_START → 业务写 → XA_END → XA_PREPARE` |
| `POST /api/v1/txn/branches/{xid}/commit` | `require_service("txn")` | TM 驱动提交 |
| `POST /api/v1/txn/branches/{xid}/rollback` | `require_service("txn")` | TM 驱动回滚 |
| `GET /api/v1/txn/branches/{xid}` | `require_service("txn")` | 分支状态核验（TM 决定点前核验） |
| `GET /api/v1/txn/branches` | `require_service("txn")` | 悬挂分支列举（对账） |

`[transaction_manager].provider` 缺省 `null` ⇒ 参与方为占位实现，协议动作**明确拒绝**（`10013` / 503），
**不静默降级**。
"""

from typing import Annotated

from fastapi import Depends, Query
from pydantic import Field

from bms_core.api.base import BaseRouter, require_service
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_DICT, CONTRACT_STABLE_LIST, BaseSchema
from bms_core.schemas.common import ApiResponse
from bms_core.transaction.base import (
    TM_SERVICE_NAME,
    BaseTransactionParticipant,
    BranchOp,
    get_transaction_participant,
)

__all__ = [
    "BranchExecuteRequest",
    "BranchOpRequest",
    "BranchRecoverView",
    "BranchStateView",
    "build_branch_router",
]

ParticipantDep = Annotated[BaseTransactionParticipant, Depends(get_transaction_participant)]
DbKeyQuery = Annotated[str, Query(description="目标库键（不透明库键）")]


class BranchOpRequest(BaseSchema):
    """分支内的单个业务操作（`op` 映射参与方**已有服务层方法**）。"""

    op: str
    """操作名（参与方分支处理器注册表键；未登记即**整体否决**）。"""

    args: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="业务载荷（交给参与方已有服务层）"
    )


class BranchExecuteRequest(BaseSchema):
    """分支执行请求（由发起方给出；`ops` 按序在**同一分支**内执行）。

    一个分支＝一条 XA 事务＝一条数据库连接，故分支内的全部操作必须一次请求提交；
    调用方可把同库的多个写入合并进同一分支（如「用户-岗位 + 用户-部门」）。
    """

    xid: str
    """分支事务标识（TM 分配）。"""

    db_key: str
    """目标库键（不透明库键）。"""

    ops: Annotated[ConcurrentStableList[BranchOpRequest], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分支操作清单（按序执行；非空）"
    )


class BranchStateView(BaseSchema):
    """分支状态视图。"""

    xid: str
    """分支事务标识。"""

    state: str
    """分支状态（active / prepared / committed / rolled_back / rejected）。"""


class BranchRecoverView(BaseSchema):
    """悬挂分支列举视图。"""

    db_key: str
    """目标库键。"""

    xids: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="悬挂分支 `xid` 文本形态清单"
    )


def build_branch_router(*, key: str = "txn_branches", prefix: str = "/txn/branches") -> BaseRouter:
    """构造参与端点路由器（供参与方服务 `service_routers()` 挂载）。

    Args:
        key: 路由登记键（服务级登记表用）。
        prefix: 挂载前缀（相对 `/api/v1`）。

    Returns:
        BaseRouter: 参与端点路由器。
    """
    router = BaseRouter(key=key, prefix=prefix, tags=["txn"])

    @router.post("", dependencies=[Depends(require_service())])
    async def execute_branch(  # pyright: ignore[reportUnusedFunction]
        req: BranchExecuteRequest, participant: ParticipantDep
    ) -> ApiResponse[BranchStateView]:
        """执行分支（单请求内 `XA_START → 业务写 → XA_END → XA_PREPARE`）。

        Args:
            req: 分支执行请求。
            participant: 应用装配的参与方。

        Returns:
            ApiResponse: 统一响应，data 为分支状态。
        """
        ops: ConcurrentStableList[BranchOp] = ConcurrentStableList()
        for item in req.ops:
            ops.add(BranchOp(op=item.op, args=item.args))
        state = await participant.execute_branch(xid=req.xid, db_key=req.db_key, ops=tuple(ops))
        return ApiResponse.ok(BranchStateView(xid=req.xid, state=state))

    @router.post("/{xid}/commit", dependencies=[Depends(require_service(TM_SERVICE_NAME))])
    async def commit_branch(  # pyright: ignore[reportUnusedFunction]
        xid: str, participant: ParticipantDep, db_key: DbKeyQuery
    ) -> ApiResponse[BranchStateView]:
        """提交分支（TM 驱动）。

        Args:
            xid: 分支事务标识。
            participant: 应用装配的参与方。
            db_key: 目标库键。

        Returns:
            ApiResponse: 统一响应，data 为分支状态。
        """
        state = await participant.commit_branch(xid=xid, db_key=db_key)
        return ApiResponse.ok(BranchStateView(xid=xid, state=state))

    @router.post("/{xid}/rollback", dependencies=[Depends(require_service(TM_SERVICE_NAME))])
    async def rollback_branch(  # pyright: ignore[reportUnusedFunction]
        xid: str, participant: ParticipantDep, db_key: DbKeyQuery
    ) -> ApiResponse[BranchStateView]:
        """回滚分支（TM 驱动）。

        Args:
            xid: 分支事务标识。
            participant: 应用装配的参与方。
            db_key: 目标库键。

        Returns:
            ApiResponse: 统一响应，data 为分支状态。
        """
        state = await participant.rollback_branch(xid=xid, db_key=db_key)
        return ApiResponse.ok(BranchStateView(xid=xid, state=state))

    @router.get("/{xid}", dependencies=[Depends(require_service(TM_SERVICE_NAME))])
    async def branch_state(  # pyright: ignore[reportUnusedFunction]
        xid: str, participant: ParticipantDep, db_key: DbKeyQuery
    ) -> ApiResponse[BranchStateView]:
        """查询分支状态（TM 决定点前核验）。

        Args:
            xid: 分支事务标识。
            participant: 应用装配的参与方。
            db_key: 目标库键。

        Returns:
            ApiResponse: 统一响应，data 为分支状态。
        """
        state = await participant.branch_state(xid=xid, db_key=db_key)
        return ApiResponse.ok(BranchStateView(xid=xid, state=state))

    @router.get("", dependencies=[Depends(require_service(TM_SERVICE_NAME))])
    async def recover_branches(  # pyright: ignore[reportUnusedFunction]
        participant: ParticipantDep, db_key: DbKeyQuery
    ) -> ApiResponse[BranchRecoverView]:
        """列举悬挂分支（对账）。

        Args:
            participant: 应用装配的参与方。
            db_key: 目标库键。

        Returns:
            ApiResponse: 统一响应，data 为悬挂分支清单。
        """
        xids = await participant.recover_branches(db_key=db_key)
        return ApiResponse.ok(BranchRecoverView(db_key=db_key, xids=ConcurrentStableList(xids)))

    return router
