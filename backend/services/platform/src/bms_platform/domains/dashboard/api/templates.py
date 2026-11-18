"""模板管理端点：`/api/v1/dashboard/templates`（11_01）。

- **鉴权**：读端点 `dashboard:query`、写端点 `dashboard:manage`；`scope=platform` 的写操作**再判平台超管**；
- **唯一性**：平台默认模板仅一份（`40306`）、一角色至多一份（`40307`）；角色须存在且启用（`40305`）；
- **删除即回退**：平台模板删后回退内置最小布局；角色模板删后该角色回退平台默认。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.dashboard.api.deps import RoleTypesDep, ServiceDep
from bms_platform.domains.dashboard.schemas.template import (
    DashboardTemplateCreate,
    DashboardTemplateDeleteResult,
    DashboardTemplateList,
    DashboardTemplateRow,
    DashboardTemplateUpdate,
)

__all__ = ["router"]

router = BaseRouter(
    key="dashboard_templates",
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("dashboard:query"))
_REQUIRE_MANAGE = Depends(require_permission("dashboard:manage"))

ScopeQuery = Annotated[str | None, Query(max_length=16, description="层级筛选（platform / role）")]


@router.get("/templates", dependencies=[_REQUIRE_QUERY])
async def list_templates(service: ServiceDep, scope: ScopeQuery = None) -> ApiResponse[DashboardTemplateList]:
    """模板列表（平台在前，角色按主键升序）。

    需要 `dashboard:query`。

    Args:
        service: 工作台服务。
        scope: 层级筛选（可选）。

    Returns:
        ApiResponse[DashboardTemplateList]: 统一响应，data 为模板清单。
    """
    items: ConcurrentStableList[DashboardTemplateRow] = await service.list_templates(scope=scope)
    return ApiResponse.ok(DashboardTemplateList(items=items, total=len(items)))


@router.post("/templates", dependencies=[_REQUIRE_MANAGE])
async def create_template(
    service: ServiceDep, roles: RoleTypesDep, payload: DashboardTemplateCreate
) -> ApiResponse[DashboardTemplateRow]:
    """新建模板。

    需要 `dashboard:manage`；平台层级要求平台超管。

    Args:
        service: 工作台服务。
        roles: 当前用户角色集（平台层级判定）。
        payload: 新建请求。

    Returns:
        ApiResponse[DashboardTemplateRow]: 统一响应，data 为新建的模板行。
    """
    return ApiResponse.ok(await service.create_template(payload=payload, role_types=roles))


@router.put("/templates/{template_id}", dependencies=[_REQUIRE_MANAGE])
async def update_template(
    service: ServiceDep, roles: RoleTypesDep, template_id: int, payload: DashboardTemplateUpdate
) -> ApiResponse[DashboardTemplateRow]:
    """编辑模板（`scope` 与 `role_id` 不可改）。

    需要 `dashboard:manage`；平台层级要求平台超管。

    Args:
        service: 工作台服务。
        roles: 当前用户角色集（平台层级判定）。
        template_id: 模板主键。
        payload: 编辑请求。

    Returns:
        ApiResponse[DashboardTemplateRow]: 统一响应，data 为更新后的模板行。
    """
    return ApiResponse.ok(await service.update_template(template_id=template_id, payload=payload, role_types=roles))


@router.delete("/templates/{template_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_template(
    service: ServiceDep, roles: RoleTypesDep, template_id: int
) -> ApiResponse[DashboardTemplateDeleteResult]:
    """删除模板。

    需要 `dashboard:manage`；平台层级要求平台超管。

    Args:
        service: 工作台服务。
        roles: 当前用户角色集（平台层级判定）。
        template_id: 模板主键。

    Returns:
        ApiResponse[DashboardTemplateDeleteResult]: 统一响应，data 为删除结果。
    """
    applied = await service.delete_template(template_id=template_id, role_types=roles)
    return ApiResponse.ok(DashboardTemplateDeleteResult(applied=applied))
