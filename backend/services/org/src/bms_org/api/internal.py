"""组织主数据服务内部端点：`/api/v1/org/internal/credentials/*`（服务间调用，不经网关）。

- **鉴权**：模块级 `require_service("identity")`——仅接受签发方 `sub=identity` 的有效服务 JWT（`aud=service`）；
  用户票据与网关服务票据（`sub=gateway`）一律拒（避免经网关被误信）。
- **租户**：由服务 JWT 的 `tenant` claim 经全局租户中间件解析租户库（未走租户豁免）。
- **契约**：计入 org 公开契约（`deploy/contracts/org.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import get_password_hasher, get_uow
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BasePasswordHasher
from bms_org.repositories.user import UserRepository
from bms_org.schemas.credentials import (
    CredentialVerifyRequest,
    CredentialVerifyResult,
    LoginStateRequest,
    LoginStateResult,
    UpdatePasswordRequest,
    UpdatePasswordResult,
)
from bms_org.services.credentials import CredentialService

router = BaseRouter(
    key="org_internal_credentials",
    prefix="/org/internal/credentials",
    tags=["org-internal"],
    dependencies=[Depends(require_service("identity"))],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
HasherDep = Annotated[BasePasswordHasher, Depends(get_password_hasher)]


def _service(uow: UowDep, hasher: HasherDep) -> CredentialService:
    """构造内部凭据服务（请求级会话 + 口令哈希实现）。

    Args:
        uow: 请求级工作单元（写事务绑主库会话）。
        hasher: 口令哈希实现。

    Returns:
        CredentialService: 凭据服务实例。
    """
    return CredentialService(UserRepository(cast("DbSession", uow.session)), hasher, uow)


@router.post("/verify")
async def verify_credential(
    req: CredentialVerifyRequest,
    uow: UowDep,
    hasher: HasherDep,
) -> ApiResponse[CredentialVerifyResult]:
    """校验账号口令（命中且参数过期时同请求内重哈希回写）。

    Args:
        req: 凭据校验请求（账号 + 口令）。
        uow: 请求级工作单元。
        hasher: 口令哈希实现。

    Returns:
        ApiResponse: 统一响应，data 为校验结果（`CredentialVerifyResult`）。
    """
    result = await _service(uow, hasher).verify(req.account, req.password)
    return ApiResponse.ok(result)


@router.post("/update-password")
async def update_password(
    req: UpdatePasswordRequest,
    uow: UowDep,
    hasher: HasherDep,
) -> ApiResponse[UpdatePasswordResult]:
    """更新账号密码（新哈希 + 变更时间 + 历史密码保留）。

    Args:
        req: 密码更新请求。
        uow: 请求级工作单元。
        hasher: 口令哈希实现。

    Returns:
        ApiResponse: 统一响应，data 为更新结果（`UpdatePasswordResult`）。
    """
    result = await _service(uow, hasher).update_password(req.account, req.new_password, keep_history=req.keep_history)
    return ApiResponse.ok(result)


@router.post("/login-state")
async def apply_login_state(
    req: LoginStateRequest,
    uow: UowDep,
    hasher: HasherDep,
) -> ApiResponse[LoginStateResult]:
    """写回登录态（成功清零并记录登录时间；失败累计并锁定）。

    Args:
        req: 登录态写回请求。
        uow: 请求级工作单元。
        hasher: 口令哈希实现（未使用，保持服务构造一致）。

    Returns:
        ApiResponse: 统一响应，data 为登录态结果（`LoginStateResult`）。
    """
    result = await _service(uow, hasher).apply_login_state(
        req.account, success=req.success, failed_count=req.failed_count, lock_seconds=req.lock_seconds
    )
    return ApiResponse.ok(result)
