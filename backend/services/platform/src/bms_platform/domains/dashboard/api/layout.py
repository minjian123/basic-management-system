"""个人布局端点：`/api/v1/dashboard/layout`（GET 解析 / PUT 保存 / DELETE 重置，11_01）。

- **鉴权**：模块级 `require_auth`；个人布局是登录用户对自身数据的操作，**不设权限码**；
- **三级回退**：个人 → 角色模板 → 平台默认 → 内置最小布局（服务端一次性解析，前端不做级联）；
- **保存严格、读取容错**：保存拒越界 / 重叠 / 非法引用；读取剔除失效卡片并给告警。
"""

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.schemas.common import ApiResponse
from bms_platform.api.locale import accept_locale, locale_scope
from bms_platform.domains.dashboard.api.deps import RoleTypesDep, ServiceDep, UserIdDep
from bms_platform.domains.dashboard.schemas.layout import (
    DashboardLayoutResetResult,
    DashboardLayoutResolve,
    DashboardLayoutSaveRequest,
    DashboardLayoutSaveResult,
)

__all__ = ["router"]

router = BaseRouter(
    key="dashboard_layout",
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)


@router.get("/layout")
async def get_layout(
    request: Request, service: ServiceDep, user_id: UserIdDep, roles: RoleTypesDep
) -> ApiResponse[DashboardLayoutResolve]:
    """解析当前用户布局（三级回退 + 可选卡片清单）。

    登录即可；卡片名按 `Accept-Language` 本地化。

    Args:
        request: 请求对象（取请求语言）。
        service: 工作台服务。
        user_id: 当前用户主键。
        roles: 当前用户角色集。

    Returns:
        ApiResponse[DashboardLayoutResolve]: 统一响应，data 为布局与可选卡片清单。
    """
    return ApiResponse.ok(
        await service.resolve_layout(user_id=user_id, role_types=roles, locale=accept_locale(request))
    )


@router.put("/layout")
async def save_layout(
    service: ServiceDep, user_id: UserIdDep, payload: DashboardLayoutSaveRequest
) -> ApiResponse[DashboardLayoutSaveResult]:
    """保存个人布局（整份覆盖）。

    登录即可；结构非法 `40304`、引用未注册卡片 `40301`。

    Args:
        service: 工作台服务。
        user_id: 当前用户主键。
        payload: 保存请求。

    Returns:
        ApiResponse[DashboardLayoutSaveResult]: 统一响应，data 为保存结果与告警。
    """
    return ApiResponse.ok(await service.save_layout(user_id=user_id, layout_config=payload.layout))


@router.delete("/layout")
async def reset_layout(service: ServiceDep, user_id: UserIdDep) -> ApiResponse[DashboardLayoutResetResult]:
    """一键重置个人布局（回退角色模板 / 平台默认 / 内置最小布局）。

    登录即可。

    Args:
        service: 工作台服务。
        user_id: 当前用户主键。

    Returns:
        ApiResponse[DashboardLayoutResetResult]: 统一响应，data 为是否删除到既有个人布局。
    """
    return ApiResponse.ok(await service.reset_layout(user_id=user_id))
