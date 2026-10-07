"""平台服务内部端点：用户概要 / 重置目标 / 统一建号 + **用户只读查询出口**（服务间调用，不经网关）。

- **鉴权**：两条路由各按调用方白名单分道——
  - `router`（`/profile`、`/reset-target`、`/create`）：`require_service("identity")`；
  - `query_router`（`/query`，**用户只读出口**）：`require_service("org")`——仅 mdm 组织服务可读。
  两者均只接受对应签发方的有效服务 JWT（`aud=service`）；用户票据与网关服务票据（`sub=gateway`）一律拒
  （避免经网关被误信）。
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库。
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_tenant, get_tenant_membership_store, get_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageResponse
from bms_core.tenant.membership import TenantMembershipStore
from bms_platform.models.user import SysUser
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import (
    InternalUserItem,
    InternalUserQueryRequest,
    UserCreateRequest,
    UserCreateResult,
    UserProfileRequest,
    UserProfileResult,
    UserResetTargetRequest,
    UserResetTargetResult,
)
from bms_platform.services.users import (
    USER_STATUSES,
    InternalUserQueryService,
    UserCreateService,
    UserProfileService,
    UserResetTargetService,
)

router = BaseRouter(
    key="platform_internal_users",
    prefix="/platform/internal/users",
    tags=["platform-internal"],
    dependencies=[Depends(require_service("identity"))],
)

MDM_ORG_SERVICE = "org"
"""允许调用**用户只读查询出口**的调用方服务标识（mdm 组织服务键 `org`）。

组织主数据（部门 / 岗位 / 人员）归 mdm、用户（账号）归 platform；mdm 组织域只读出口据此取用户明细，
故白名单只登记 mdm 组织服务；后续接入方按需追加。
"""

query_router = BaseRouter(
    key="platform_internal_users_query",
    prefix="/platform/internal/users",
    tags=["platform-internal"],
    dependencies=[Depends(require_service(MDM_ORG_SERVICE))],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
MembershipDep = Annotated[TenantMembershipStore, Depends(get_tenant_membership_store)]


@router.post("/profile")
async def user_profile(req: UserProfileRequest, uow: UowDep) -> ApiResponse[UserProfileResult]:
    """按主键取用户概要（不存在 `found=false`，由调用侧判定错误语义）。

    Args:
        req: 概要查询请求（用户主键）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为概要结果（`UserProfileResult`）。
    """
    service = UserProfileService(UserRepository(cast("DbSession", uow.session)))
    return ApiResponse.ok(await service.profile(req.user_id))


@router.post("/reset-target")
async def reset_target(req: UserResetTargetRequest, uow: UowDep) -> ApiResponse[UserResetTargetResult]:
    """按标识（账号 / 手机 / 邮箱）解析找回密码投递目标（不存在 / 不可送达由调用侧统一防枚举处理）。

    Args:
        req: 重置目标查询请求（标识）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为解析结果（`UserResetTargetResult`）。
    """
    service = UserResetTargetService(UserRepository(cast("DbSession", uow.session)))
    return ApiResponse.ok(await service.resolve(req.identifier))


@router.post("/create")
async def create_user(
    req: UserCreateRequest,
    uow: UowDep,
    tenant: TenantDep,
    membership: MembershipDep,
) -> ApiResponse[UserCreateResult]:
    """统一建号入口（用户名空闲即建；撞名 `created=false`，由调用侧换后缀重试）。

    建号成功后经关系数据源维护「用户↔归属租户」可达关系（失败不阻断建号）。

    Args:
        req: 建号请求（账号 / 昵称 / 语言时区 / 来源）。
        uow: 请求级工作单元。
        tenant: 解析链租户上下文（归属租户）。
        membership: 关系数据源（服务间调用；本服务为远端实现）。

    Returns:
        ApiResponse: 统一响应，data 为建号结果（`UserCreateResult`）。
    """
    service = UserCreateService(UserRepository(cast("DbSession", uow.session)), uow, membership=membership)
    tenant_id = tenant.tenant_id if tenant is not None else None
    return ApiResponse.ok(
        await service.create_user(
            username=req.username,
            name=req.name,
            locale=req.locale,
            timezone=req.timezone,
            source=req.source,
            owner_tenant_id=tenant_id,
        )
    )


def _require_status(status: str | None) -> None:
    """校验状态筛选值。

    Args:
        status: 状态（可空）。

    Raises:
        ParamError: 取值非法（10001）。
    """
    if status is not None and status not in USER_STATUSES:
        raise ParamError(f"账号状态非法：{status}")


def _internal_item(row: SysUser) -> InternalUserItem:
    """用户记录 → 内部只读行。

    不含口令哈希 / 失败计数 / 锁定字段 / 策略字段；`dept_id` 字段未落地时恒 `None`。

    Args:
        row: 用户记录。

    Returns:
        InternalUserItem: 内部只读行。
    """
    return InternalUserItem(
        id=row.id,
        username=row.username,
        name=row.name,
        status=row.status or "",
        phone=row.phone,
        email=row.email,
        dept_id=None,
    )


@query_router.post("/query")
async def query_users(req: InternalUserQueryRequest, uow: UowDep) -> ApiResponse[BasePageResponse[InternalUserItem]]:
    """按关键字 / 状态 / 限定集合分页查询用户（**服务间只读出口**）。

    供 mdm 组织域只读出口（组织数据源 `users` / 名称回显 `resolve_names(user)` / 按用户解析角色）
    取用户明细——**不跨库读** `sys_user`。仅接受 `sub=org` 服务票据；只读、不写库、不产事件；
    联系方式**原样返回**（脱敏归消费方 mdm 出口）。

    Args:
        req: 查询请求（关键字 / 状态 / 限定集合 / 分页）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为分页用户只读行（主键升序）。
    """
    _require_status(req.status)
    service = InternalUserQueryService(UserRepository(cast("DbSession", uow.session)))
    rows, total = await service.query(
        keyword=req.keyword,
        status=req.status,
        ids=req.ids,
        page=req.page,
        size=req.size,
    )
    items = ConcurrentStableList(_internal_item(row) for row in rows)
    return ApiResponse.ok(BasePageResponse[InternalUserItem](list=items, total=total, page=req.page, size=req.size))
