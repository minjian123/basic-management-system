"""用户↔租户可达关系内部端点：`/api/v1/tenant/internal/memberships`（服务间调用，不经网关；11_01）。

- **鉴权**：模块级 `require_service("org", "identity")`——仅接受签发方为 `org` / `identity` 的
  有效服务 JWT（`aud=service`）；用户票据与网关服务票据（`sub=gateway`）一律拒。
- **资源式**：`GET`（读目标集合） / `POST`（建 / 复活） / `DELETE`（回收）；三者统一返回
  `TenantMembershipListResponse`（操作后该用户有效目标集合）。
- **显式归属租户**：请求体 / 查询参数显式传 `owner_tenant_id`（用户归属租户），不依赖服务 JWT 租户位。
- **契约**：计入 tenant 公开契约（`deploy/contracts/tenant.json`）；新增端点属非破坏性变更。
"""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_service
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import SessionFactory, session_scope
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.schemas.common import ApiResponse
from bms_core.tenant.membership import (
    TenantMembershipGrantRequest,
    TenantMembershipListResponse,
    TenantMembershipTarget,
)
from bms_tenant.repositories.tenant_membership import TenantMembershipRepository
from bms_tenant.services.membership import TenantMembershipService

router = BaseRouter(
    key="tenant_membership",
    prefix="/tenant/internal/memberships",
    tags=["tenant-internal"],
    dependencies=[Depends(require_service("org", "identity"))],
)

OwnerTenantQuery = Annotated[int, Query(gt=0, description="归属租户主键（用户建号 / 登录所在租户）")]
UserQuery = Annotated[int, Query(gt=0, description="用户主键（org 服务 sys_user.id）")]
TargetTenantQuery = Annotated[int | None, Query(gt=0, description="目标租户主键（省略＝回收该用户全部）")]
IncludeDisabledQuery = Annotated[bool, Query(description="是否含 disabled 行（缺省只取有效行）")]


async def get_membership_service(request: Request) -> AsyncIterator[TenantMembershipService]:
    """请求级关系服务（平台服务库会话 + 工作单元；退出即释放）。

    Args:
        request: 请求对象。

    Yields:
        TenantMembershipService: 会话绑定的关系服务。
    """
    registry = cast("EngineRegistry", request.app.state.engine_registry)
    factory = cast("SessionFactory | None", getattr(request.app.state, "session_factory", None))
    async with session_scope(registry, db_key=PLATFORM_DB_KEY, factory=factory) as session:
        yield TenantMembershipService(TenantMembershipRepository(session), DbUnitOfWork(session))


ServiceDep = Annotated[TenantMembershipService, Depends(get_membership_service)]


async def _overview(
    service: TenantMembershipService, *, owner_tenant_id: int, user_id: int
) -> TenantMembershipListResponse:
    """取操作后该用户的有效目标集合。

    Args:
        service: 关系服务。
        owner_tenant_id: 归属租户主键。
        user_id: 用户主键。

    Returns:
        TenantMembershipListResponse: 有效目标集合响应。
    """
    targets: ConcurrentStableList[TenantMembershipTarget] = await service.list_targets(
        tenant_id=owner_tenant_id, user_id=user_id
    )
    return TenantMembershipListResponse(targets=targets)


@router.get("")
async def list_memberships(
    service: ServiceDep,
    owner_tenant_id: OwnerTenantQuery,
    user_id: UserQuery,
    include_disabled: IncludeDisabledQuery = False,
) -> ApiResponse[TenantMembershipListResponse]:
    """读某用户可访问目标租户集合（可选含 `disabled` 行，供读路径自愈判据）。

    Args:
        service: 关系服务。
        owner_tenant_id: 归属租户主键。
        user_id: 用户主键。
        include_disabled: 是否含 `disabled` 行。

    Returns:
        ApiResponse: 统一响应，data 为目标集合。
    """
    targets = await service.list_targets(tenant_id=owner_tenant_id, user_id=user_id, include_disabled=include_disabled)
    return ApiResponse.ok(TenantMembershipListResponse(targets=targets))


@router.post("")
async def ensure_membership(
    req: TenantMembershipGrantRequest, service: ServiceDep
) -> ApiResponse[TenantMembershipListResponse]:
    """建立 / 复活关系（幂等）。

    Args:
        req: 写入请求（归属租户 / 用户 / 目标租户 / 来源）。
        service: 关系服务。

    Returns:
        ApiResponse: 统一响应，data 为操作后该用户有效目标集合。
    """
    await service.ensure(
        tenant_id=req.owner_tenant_id,
        user_id=req.user_id,
        target_tenant_id=req.target_tenant_id,
        source=req.source,
    )
    return ApiResponse.ok(await _overview(service, owner_tenant_id=req.owner_tenant_id, user_id=req.user_id))


@router.delete("")
async def revoke_membership(
    service: ServiceDep,
    owner_tenant_id: OwnerTenantQuery,
    user_id: UserQuery,
    target_tenant_id: TargetTenantQuery = None,
) -> ApiResponse[TenantMembershipListResponse]:
    """回收关系（置 `disabled`，幂等；省略目标租户则回收该用户全部）。

    Args:
        service: 关系服务。
        owner_tenant_id: 归属租户主键。
        user_id: 用户主键。
        target_tenant_id: 目标租户主键（省略＝回收全部）。

    Returns:
        ApiResponse: 统一响应，data 为操作后该用户有效目标集合。
    """
    if target_tenant_id is None:
        await service.revoke_all(tenant_id=owner_tenant_id, user_id=user_id)
    else:
        await service.revoke(tenant_id=owner_tenant_id, user_id=user_id, target_tenant_id=target_tenant_id)
    return ApiResponse.ok(await _overview(service, owner_tenant_id=owner_tenant_id, user_id=user_id))
