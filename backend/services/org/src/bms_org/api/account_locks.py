"""组织主数据服务管理端点：`/api/v1/org/locks`（锁定记录列表 / 详情 / 手动锁定 / 解锁）。

- **鉴权**：模块级 `require_auth`（登录态）；各端点挂 `require_permission("user:query" / "user:lock" / "user:unlock")`
  ——permission 基座当前为 Null（恒定通过）= RBAC 前平台超管口径，RBAC 就绪后自动收口。
- **租户**：由登录态解析租户，`get_uow` 依租户库键取 org 租户库会话（与内部端点同口径）。
- **留痕**：手动锁定 / 解锁接 `AuditCapturer` 占位（阶段八接真实落库）+ 结构化日志。
- **契约**：计入 org 公开契约（`deploy/contracts/org.json`）；新增端点属非破坏性变更。
"""

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_audit_capturer, get_config_source, get_uow
from bms_core.audit.base import AuditCapturer
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_org.models.account_lock import LOCK_TYPES, SysAccountLock
from bms_org.repositories.account_lock import AccountLockRepository
from bms_org.repositories.user import UserRepository
from bms_org.schemas.account_lock import LockItem, ManualLockRequest
from bms_org.services.account_lock import AccountLockService

router = BaseRouter(
    key="org_account_locks",
    prefix="/org/locks",
    tags=["org-locks"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
UserIdQuery = Annotated[int | None, Query(description="用户主键（精确）")]
LockTypeQuery = Annotated[str | None, Query(description="锁定类型（fail_limit/inactive/manual）")]
ActiveQuery = Annotated[bool | None, Query(description="是否生效中（未解锁且未到期；缺省=全部）")]
LockedFromQuery = Annotated[datetime | None, Query(description="锁定时间下界（UTC，闭区间）")]
LockedToQuery = Annotated[datetime | None, Query(description="锁定时间上界（UTC，闭区间）")]

_REQUIRE_QUERY = Depends(require_permission("user:query"))
_REQUIRE_LOCK = Depends(require_permission("user:lock"))
_REQUIRE_UNLOCK = Depends(require_permission("user:unlock"))

_TABLE = "sys_account_lock"


def _service(uow: UowDep, config: ConfigDep) -> AccountLockService:
    """构造账号锁定服务（请求级会话）。

    Args:
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        AccountLockService: 账号锁定服务实例。
    """
    session = cast("DbSession", uow.session)
    return AccountLockService(UserRepository(session), AccountLockRepository(session), uow, config)


def _to_item(lock: SysAccountLock) -> LockItem:
    """锁定记录 → 契约。

    Args:
        lock: 锁定记录。

    Returns:
        LockItem: 锁定记录行契约。
    """
    return LockItem(
        id=lock.id,
        user_id=lock.user_id,
        lock_type=lock.lock_type,
        reason=lock.reason,
        locked_at=lock.locked_at,
        locked_by=lock.locked_by,
        expire_at=lock.expire_at,
        unlock_at=lock.unlock_at,
        unlock_by=lock.unlock_by,
        unlock_mode=lock.unlock_mode,
    )


def _require_lock_type(lock_type: str | None) -> None:
    """校验锁定类型筛选值。

    Args:
        lock_type: 锁定类型（可空）。

    Raises:
        ParamError: 取值非法（10001）。
    """
    if lock_type is not None and lock_type not in LOCK_TYPES:
        raise ParamError(f"锁定类型非法：{lock_type}")


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_locks(
    query: PageDep,
    uow: UowDep,
    config: ConfigDep,
    user_id: UserIdQuery = None,
    lock_type: LockTypeQuery = None,
    active: ActiveQuery = None,
    locked_from: LockedFromQuery = None,
    locked_to: LockedToQuery = None,
) -> ApiResponse[BasePageResponse[LockItem]]:
    """锁定记录列表（筛选 + 分页）。

    Args:
        query: 分页与排序参数。
        uow: 请求级工作单元。
        config: 系统参数取数。
        user_id: 用户主键（精确）。
        lock_type: 锁定类型（精确）。
        active: 是否生效中。
        locked_from: 锁定时间下界（UTC）。
        locked_to: 锁定时间上界（UTC）。

    Returns:
        ApiResponse: 统一响应，data 为分页锁定记录列表。
    """
    _require_lock_type(lock_type)
    items, total = await _service(uow, config).list_locks(
        query,
        user_id=user_id,
        lock_type=lock_type,
        active=active,
        locked_from=locked_from,
        locked_to=locked_to,
    )
    return ApiResponse.ok(
        BasePageResponse[LockItem](
            list=ConcurrentStableList(_to_item(item) for item in items), total=total, page=query.page, size=query.size
        )
    )


@router.get("/{lock_id}", dependencies=[_REQUIRE_QUERY])
async def get_lock(lock_id: int, uow: UowDep, config: ConfigDep) -> ApiResponse[LockItem]:
    """锁定记录详情（含已解锁）。

    Args:
        lock_id: 锁定记录主键。
        uow: 请求级工作单元。
        config: 系统参数取数。

    Returns:
        ApiResponse: 统一响应，data 为锁定记录行。
    """
    record = await _service(uow, config).detail(lock_id)
    return ApiResponse.ok(_to_item(record))


@router.post("", dependencies=[_REQUIRE_LOCK])
async def lock_account(
    req: ManualLockRequest, uow: UowDep, config: ConfigDep, audit: AuditDep
) -> ApiResponse[LockItem]:
    """手动锁定账号（`manual` 型；已生效锁幂等返回既有）。

    Args:
        req: 手动锁定请求（用户主键 + 原因）。
        uow: 请求级工作单元。
        config: 系统参数取数。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为锁定记录行。
    """
    actor = current_user_id.get()
    lock = await _service(uow, config).lock_manual(req.user_id, reason=req.reason, actor=actor)
    audit.capture(table=_TABLE, model_id=lock.id, changes=ConcurrentStableList(), actor=actor)
    return ApiResponse.ok(_to_item(lock))


@router.put("/{lock_id}/unlock", dependencies=[_REQUIRE_UNLOCK])
async def unlock_account(lock_id: int, uow: UowDep, config: ConfigDep, audit: AuditDep) -> ApiResponse[LockItem]:
    """手动解锁（清账号锁定状态 + 回填解锁信息 + 留痕）。

    Args:
        lock_id: 锁定记录主键。
        uow: 请求级工作单元。
        config: 系统参数取数。
        audit: 审计捕获（占位）。

    Returns:
        ApiResponse: 统一响应，data 为解锁后的锁定记录行。
    """
    actor = current_user_id.get()
    lock = await _service(uow, config).unlock(lock_id, actor=actor)
    audit.capture(table=_TABLE, model_id=lock.id, changes=ConcurrentStableList(), actor=actor)
    return ApiResponse.ok(_to_item(lock))
