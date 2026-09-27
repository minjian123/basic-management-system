"""组织主数据服务内部端点：`/api/v1/org/internal/users/profile`（服务间调用，不经网关）。

- **鉴权**：模块级 `require_service("identity")`——仅接受签发方 `sub=identity` 的有效服务 JWT（`aud=service`）；
  用户票据与网关服务票据（`sub=gateway`）一律拒（避免经网关被误信）。
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库。
- **契约**：计入 org 公开契约（`deploy/contracts/org.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_uow
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_org.repositories.user import UserRepository
from bms_org.schemas.users import (
    UserCreateRequest,
    UserCreateResult,
    UserProfileRequest,
    UserProfileResult,
    UserResetTargetRequest,
    UserResetTargetResult,
)
from bms_org.services.users import UserCreateService, UserProfileService, UserResetTargetService

router = BaseRouter(
    key="org_internal_users",
    prefix="/org/internal/users",
    tags=["org-internal"],
    dependencies=[Depends(require_service("identity"))],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]


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
async def create_user(req: UserCreateRequest, uow: UowDep) -> ApiResponse[UserCreateResult]:
    """JIT 建号（用户名空闲即建；撞名 `created=false`，由调用侧换后缀重试）。

    Args:
        req: 建号请求（账号 / 昵称 / 语言时区）。
        uow: 请求级工作单元。

    Returns:
        ApiResponse: 统一响应，data 为建号结果（`UserCreateResult`）。
    """
    service = UserCreateService(UserRepository(cast("DbSession", uow.session)), uow)
    return ApiResponse.ok(
        await service.create_user(
            username=req.username,
            name=req.name,
            locale=req.locale,
            timezone=req.timezone,
        )
    )
