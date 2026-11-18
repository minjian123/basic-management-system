"""首页工作台路由公共依赖：服务构造 + 当前用户角色集（四个路由共用）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from bms_core.api.deps import get_cache_region, get_preference_store, get_service_client, get_uow
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import get_current_user_id
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.preference.base import BasePreferenceStore
from bms_core.servicecall.base import BaseServiceClient
from bms_platform.domains.dashboard.services.dashboard import DashboardService
from bms_platform.wiring import build_dashboard_role_port, build_dashboard_service

__all__ = ["RoleTypesDep", "ServiceDep", "UserIdDep", "current_roles", "current_user_id", "dashboard_service"]


def dashboard_service(
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
    preferences: Annotated[BasePreferenceStore, Depends(get_preference_store)],
    service_client: Annotated[BaseServiceClient, Depends(get_service_client)],
) -> DashboardService:
    """构造请求级工作台服务（装配面统一构造，域内不 import 他域实现）。

    Args:
        tenant_uow: 租户库工作单元。
        cache: 缓存 Region。
        preferences: 用户偏好存储（个人布局）。
        service_client: 服务间调用客户端（未读角标）。

    Returns:
        DashboardService: 工作台服务实例。
    """
    return build_dashboard_service(
        tenant_uow=tenant_uow,
        cache=cache,
        preferences=preferences,
        service_client=service_client,
    )


ServiceDep = Annotated[DashboardService, Depends(dashboard_service)]


async def current_roles(
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> ConcurrentStableList[tuple[str, int]]:
    """取当前用户直接角色集（`(role_type, role_id)` 插入序）。

    Args:
        tenant_uow: 租户库工作单元。

    Returns:
        ConcurrentStableList[tuple[str, int]]: 角色类型与主键（未登录为空）。
    """
    user_id = get_current_user_id()
    if user_id is None:
        return ConcurrentStableList()
    return await build_dashboard_role_port(tenant_uow).roles_of_user(user_id)


RoleTypesDep = Annotated[ConcurrentStableList[tuple[str, int]], Depends(current_roles)]


def current_user_id() -> int:
    """取当前用户主键（路由均要求登录态；缺失按 0 兜底，不参与任何写判定）。

    Returns:
        int: 用户主键；无登录上下文为 0。
    """
    return get_current_user_id() or 0


UserIdDep = Annotated[int, Depends(current_user_id)]
