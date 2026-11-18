"""角标端点：`/api/v1/dashboard/badges`（11_01）。

- **登录即可**（无权限码）：顶栏 / 侧边栏角标是登录态内建能力；
- **统一出口**：待办经领域端口（工作流未落地时占位不可用）、未读经通知服务内部端点（唯一口径在通知中心）；
- **单角标降级**：任一来源不可用只把该角标标为 `available=false`，接口恒 200、不阻断整页。
"""

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_auth
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.dashboard.api.deps import ServiceDep, UserIdDep
from bms_platform.domains.dashboard.schemas.badge import DashboardBadges

__all__ = ["router"]

router = BaseRouter(
    key="dashboard_badges",
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)


@router.get("/badges")
async def get_badges(service: ServiceDep, user_id: UserIdDep) -> ApiResponse[DashboardBadges]:
    """取待办与未读角标。

    登录即可；来源不可用时对应角标 `available=false`（前端隐藏角标）。

    Args:
        service: 工作台服务。
        user_id: 当前用户主键。

    Returns:
        ApiResponse[DashboardBadges]: 统一响应，data 为待办与未读角标。
    """
    return ApiResponse.ok(await service.badges(user_id=user_id))
