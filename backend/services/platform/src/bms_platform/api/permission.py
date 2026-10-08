"""平台服务内部端点：权限快照失效（服务间调用，不经网关）。

- **鉴权**：`require_service("org")`——仅 mdm 组织服务可调用（岗位 / 部门 / 角色分配变更后触发）；
  用户票据与网关服务票据一律拒（避免经网关被误信）；
- **语义**：租户权限版本 +1（`user_ids` 为空即全租户）；给定用户时顺带删除其旧版本缓存键，
  使授权 / 主体链变更**即时生效**（未走事件订阅前的先行通道，事件轨见《02_04 详细设计》§9）；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更。
"""

from typing import Annotated

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_service
from bms_core.api.deps import current_tenant_id_of, get_cache_region, get_tenant
from bms_core.cache.base import CacheRegion
from bms_core.db.tenant import TenantContext
from bms_core.schemas.common import ApiResponse
from bms_platform.schemas.permission import PermissionInvalidateRequest, PermissionInvalidateResult
from bms_platform.services.permission import invalidate_permission_cache

MDM_ORG_SERVICE = "org"
"""允许调用失效端点的调用方服务标识（mdm 组织服务键 `org`）。"""

router = BaseRouter(
    key="platform_internal_permission",
    prefix="/platform/internal/permissions",
    tags=["platform-internal"],
    dependencies=[Depends(require_service(MDM_ORG_SERVICE))],
)


@router.post("/invalidate", response_model=ApiResponse[PermissionInvalidateResult], summary="失效权限快照")
async def invalidate_permissions(
    payload: PermissionInvalidateRequest,
    tenant: Annotated[TenantContext | None, Depends(get_tenant)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
) -> ApiResponse[PermissionInvalidateResult]:
    """失效当前租户的权限快照（版本 +1；可指定用户）。

    Args:
        payload: 失效请求（`user_ids` 空 = 全租户）。
        tenant: 请求级租户上下文（由服务 JWT 的 tenant claim 解析）。
        cache: 缓存能力域。

    Returns:
        ApiResponse[PermissionInvalidateResult]: 递增后的权限版本号。
    """
    version = await invalidate_permission_cache(
        cache,
        tenant_id=current_tenant_id_of(tenant),
        user_ids=tuple(payload.user_ids) if payload.user_ids else None,
    )
    return ApiResponse(data=PermissionInvalidateResult(version=version))
