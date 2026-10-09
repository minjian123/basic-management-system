"""TM 对外契约：全局事务开启 / 提交 / 回滚 / 查询。

- **鉴权**：`require_service()`——任意已登记服务均可发起（TM 是**基础设施**，与租户 / 业务无关）；
- `caller_service` **取自服务身份**（`VerifiedToken.service`），不由请求体声明；
- 计入 `txn` 服务公开契约（`deploy/contracts/txn.json`）。
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter, require_service
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.session import DbSession, get_platform_uow
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.oauth.verify import VerifiedToken
from bms_core.schemas.common import ApiResponse
from bms_core.transaction.base import BranchSpec, GlobalTransaction
from bms_txn.repositories.ledger import GlobalTxnBranchRepository, GlobalTxnRepository
from bms_txn.schemas.ledger import BeginGlobalTxnRequest, BranchView, GlobalTxnView
from bms_txn.services.coordinator import DEFAULT_DEADLINE_SECONDS, TransactionCoordinator
from bms_txn.services.driver import BranchDriver

router = BaseRouter(
    key="txn_global",
    prefix="/txn/global",
    tags=["txn"],
    dependencies=[Depends(require_service())],
)

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
ServiceDep = Annotated[VerifiedToken, Depends(require_service())]


def _driver(request: Request) -> BranchDriver:
    """取应用装配的分支驱动（未装配时明确失败，不静默成功）。

    Args:
        request: 请求对象。

    Returns:
        BranchDriver: 分支驱动实现。
    """
    driver = getattr(request.app.state, "branch_driver", None)
    if isinstance(driver, BranchDriver):
        return driver
    from bms_txn.services.driver import UnavailableBranchDriver

    return UnavailableBranchDriver()


def _coordinator(uow: UowDep, request: Request) -> TransactionCoordinator:
    """构造协调器（请求级会话 + 应用驱动）。

    Args:
        uow: 请求级工作单元（**平台库**写会话）。
        request: 请求对象（取分支驱动）。

    Returns:
        TransactionCoordinator: 协调器实例。
    """
    session = cast("DbSession", uow.session)
    settings = request.app.state.settings
    deadline = getattr(getattr(settings, "transaction_manager", None), "deadline_seconds", DEFAULT_DEADLINE_SECONDS)
    return TransactionCoordinator(
        GlobalTxnRepository(session),
        GlobalTxnBranchRepository(session),
        uow,
        _driver(request),
        deadline_seconds=float(deadline),
    )


def _to_view(snapshot: GlobalTransaction) -> GlobalTxnView:
    """契约快照 → 响应视图。

    Args:
        snapshot: 协调器返回的事务快照。

    Returns:
        GlobalTxnView: 响应视图。
    """
    branches: ConcurrentStableList[BranchView] = ConcurrentStableList()
    for ref in snapshot.branches:
        branches.add(
            BranchView(
                branch_id=ref.branch_id,
                service=ref.service,
                db_key=ref.db_key,
                xid=ref.xid,
                state=ref.state,
                retry_count=ref.retry_count,
            )
        )
    return GlobalTxnView(
        global_txn_id=snapshot.global_txn_id,
        caller_service=snapshot.caller_service,
        state=snapshot.state,
        deadline_at=snapshot.deadline_at,
        decided_at=snapshot.decided_at,
        branches=branches,
    )


@router.post("")
async def begin_global_txn(
    req: BeginGlobalTxnRequest, uow: UowDep, token: ServiceDep, request: Request
) -> ApiResponse[GlobalTxnView]:
    """开启全局事务并分配各分支 `xid`。

    Args:
        req: 开启请求（分支声明清单 + 可选超时）。
        uow: 请求级工作单元。
        token: 服务身份（`caller_service` 来源）。
        request: 请求对象（取分支驱动）。

    Returns:
        ApiResponse: 统一响应，data 为全局事务视图。
    """
    specs = ConcurrentStableList[BranchSpec]()
    for item in req.branches:
        specs.add(BranchSpec(branch_id=item.branch_id, service=item.service, db_key=item.db_key))
    snapshot = await _coordinator(uow, request).begin(
        caller_service=token.service or "", branches=tuple(specs), timeout_seconds=req.timeout_seconds
    )
    return ApiResponse.ok(_to_view(snapshot))


@router.post("/{global_txn_id}/commit")
async def commit_global_txn(
    global_txn_id: str, uow: UowDep, token: ServiceDep, request: Request
) -> ApiResponse[GlobalTxnView]:
    """请求提交（TM 核验全部分支 `prepared` 后落决定点并逐分支提交）。

    Args:
        global_txn_id: 全局事务标识。
        uow: 请求级工作单元。
        token: 服务身份（占位：TM 不校验发起方一致性，由服务身份通道保证）。
        request: 请求对象（取分支驱动）。

    Returns:
        ApiResponse: 统一响应，data 为全局事务视图。
    """
    del token
    return ApiResponse.ok(_to_view(await _coordinator(uow, request).commit(global_txn_id)))


@router.delete("/{global_txn_id}")
async def rollback_global_txn(
    global_txn_id: str, uow: UowDep, token: ServiceDep, request: Request
) -> ApiResponse[GlobalTxnView]:
    """请求回滚（决定点之前有效；之后由 TM 幂等吸收）。

    Args:
        global_txn_id: 全局事务标识。
        uow: 请求级工作单元。
        token: 服务身份（占位）。
        request: 请求对象（取分支驱动）。

    Returns:
        ApiResponse: 统一响应，data 为全局事务视图。
    """
    del token
    return ApiResponse.ok(_to_view(await _coordinator(uow, request).rollback(global_txn_id)))


@router.get("/{global_txn_id}")
async def get_global_txn(
    global_txn_id: str, uow: UowDep, token: ServiceDep, request: Request
) -> ApiResponse[GlobalTxnView]:
    """查询全局事务状态。

    Args:
        global_txn_id: 全局事务标识。
        uow: 请求级工作单元。
        token: 服务身份（占位）。
        request: 请求对象（取分支驱动）。

    Returns:
        ApiResponse: 统一响应，data 为全局事务视图。
    """
    del token
    return ApiResponse.ok(_to_view(await _coordinator(uow, request).status(global_txn_id)))
