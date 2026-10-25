"""权限元数据端点：业务码 / 动作码 / 权限码（`permission_meta` 业务域）。

- 只读清单供租户侧只读消费；写路径仅平台超管（权限码 `business:*` / `action:*` / `permission:*`）；
- 服务构造经 `bms_platform.wiring`（本域不 import 菜单表单 / 角色域实现，跨域只读面由装配面注入）。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_cache_region, get_outbox_store, get_platform_uow
from bms_core.cache.base import CacheRegion
from bms_core.core.exceptions import MenuNotFoundError
from bms_core.db.session import get_uow as get_tenant_uow
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.api.locale import locale_scope
from bms_platform.domains.permission_meta.schemas.permission_meta import (
    ActionCreateRequest,
    ActionItem,
    ActionList,
    ActionUpdateRequest,
    BusinessCreateRequest,
    BusinessItem,
    BusinessList,
    BusinessUpdateRequest,
    PermissionCreateRequest,
    PermissionGenerateRequest,
    PermissionGenerateResult,
    PermissionItem,
    PermissionList,
    PermissionUpdateRequest,
)
from bms_platform.domains.permission_meta.services.permission_meta import PermissionMetadataService
from bms_platform.wiring import build_permission_service

business_router = BaseRouter(
    key="sys_businesses",
    prefix="/businesses",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)
action_router = BaseRouter(
    key="sys_actions",
    prefix="/actions",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)
permission_router = BaseRouter(
    key="sys_permissions",
    prefix="/permissions",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
TenantUowDep = Annotated[UnitOfWork, Depends(get_tenant_uow)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]

BusinessIdQuery = Annotated[int | None, Query(gt=0, description="业务码主键（可空 = 全部）")]

_REQUIRE_BUSINESS_QUERY = Depends(require_permission("business:query"))
_REQUIRE_BUSINESS_MANAGE = Depends(require_permission("business:manage"))
_REQUIRE_ACTION_QUERY = Depends(require_permission("action:query"))
_REQUIRE_ACTION_MANAGE = Depends(require_permission("action:manage"))
_REQUIRE_PERMISSION_QUERY = Depends(require_permission("permission:query"))
_REQUIRE_PERMISSION_MANAGE = Depends(require_permission("permission:manage"))


def _service(
    uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
    tenant_uow: UnitOfWork | None = None,
) -> PermissionMetadataService:
    """构造权限元数据服务（请求级会话）。

    Args:
        uow: 请求级工作单元（平台库：业务码 / 动作码 / 权限码表）。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        tenant_uow: 租户库工作单元（角色授权引用探测；缺省不探测）。

    Returns:
        PermissionMetadataService: 权限元数据服务实例。
    """
    return build_permission_service(
        uow=uow,
        outbox=outbox,
        cache=cache,
        tenant_session=tenant_uow.session if tenant_uow is not None else None,
    )


# ------------------------------------------------------------------ 业务 / 动作码（只读）


@business_router.get("", dependencies=[_REQUIRE_BUSINESS_QUERY])
async def list_businesses(uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[BusinessList]:
    """业务权限码清单（租户侧可见、只读）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为业务码清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_businesses())


@action_router.get("", dependencies=[_REQUIRE_ACTION_QUERY])
async def list_actions(uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[ActionList]:
    """动作码清单（全局字典；平台维护视图 / 租户只读）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为动作码清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_actions())


@permission_router.get("", dependencies=[_REQUIRE_PERMISSION_QUERY])
async def list_permissions(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, business_id: BusinessIdQuery = None
) -> ApiResponse[PermissionList]:
    """权限码清单（业务码 × 动作码组合；平台维护视图 / 租户只读）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        business_id: 业务码主键（可空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为权限码清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_permissions(business_id))


# ------------------------------------------------------------------ 业务 / 动作 / 权限码（写）


@business_router.post("", dependencies=[_REQUIRE_BUSINESS_MANAGE])
async def create_business(
    req: BusinessCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[BusinessItem]:
    """新增业务码。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为业务码行。
    """
    row = await _service(uow, outbox, cache).create_business(req)
    return ApiResponse.ok(await _business_item(uow, outbox, cache, row.id))


@business_router.put("/{business_id}", dependencies=[_REQUIRE_BUSINESS_MANAGE])
async def update_business(
    business_id: int,
    req: BusinessUpdateRequest,
    uow: UowDep,
    tenant_uow: TenantUowDep,
    outbox: OutboxDep,
    cache: CacheDep,
) -> ApiResponse[BusinessItem]:
    """更新业务码（`code` 不可改；停用时连带停用其权限码）。

    Args:
        business_id: 业务码主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为业务码行。
    """
    await _service(uow, outbox, cache, tenant_uow).update_business(business_id, req)
    return ApiResponse.ok(await _business_item(uow, outbox, cache, business_id))


@business_router.delete("/{business_id}", dependencies=[_REQUIRE_BUSINESS_MANAGE])
async def delete_business(
    business_id: int, uow: UowDep, tenant_uow: TenantUowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[None]:
    """删除业务码（有条件删除）。

    Args:
        business_id: 业务码主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache, tenant_uow).delete_business(business_id)
    return ApiResponse.ok(None)


@action_router.post("", dependencies=[_REQUIRE_ACTION_MANAGE])
async def create_action(
    req: ActionCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[ActionItem]:
    """新增动作码。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为动作码行。
    """
    row = await _service(uow, outbox, cache).create_action(req)
    return ApiResponse.ok(await _action_item(uow, outbox, cache, row.id))


@action_router.put("/{action_id}", dependencies=[_REQUIRE_ACTION_MANAGE])
async def update_action(
    action_id: int,
    req: ActionUpdateRequest,
    uow: UowDep,
    tenant_uow: TenantUowDep,
    outbox: OutboxDep,
    cache: CacheDep,
) -> ApiResponse[ActionItem]:
    """更新动作码（`code` 不可改；停用时连带停用其权限码）。

    Args:
        action_id: 动作码主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为动作码行。
    """
    await _service(uow, outbox, cache, tenant_uow).update_action(action_id, req)
    return ApiResponse.ok(await _action_item(uow, outbox, cache, action_id))


@action_router.delete("/{action_id}", dependencies=[_REQUIRE_ACTION_MANAGE])
async def delete_action(
    action_id: int, uow: UowDep, tenant_uow: TenantUowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[None]:
    """删除动作码（有条件删除）。

    Args:
        action_id: 动作码主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache, tenant_uow).delete_action(action_id)
    return ApiResponse.ok(None)


@permission_router.post("", dependencies=[_REQUIRE_PERMISSION_MANAGE])
async def create_permission(
    req: PermissionCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[PermissionItem]:
    """手工新增权限码组合。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为权限码行。
    """
    row = await _service(uow, outbox, cache).create_permission(req)
    return ApiResponse.ok(await _permission_item(uow, outbox, cache, row.id))


@permission_router.post("/generate", dependencies=[_REQUIRE_PERMISSION_MANAGE])
async def generate_permissions(
    req: PermissionGenerateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[PermissionGenerateResult]:
    """批量补生成缺失的权限码组合。

    Args:
        req: 范围与是否含停用项。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为新建 / 恢复 / 跳过计数。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).generate_permissions(req))


@permission_router.put("/{permission_id}", dependencies=[_REQUIRE_PERMISSION_MANAGE])
async def update_permission(
    permission_id: int,
    req: PermissionUpdateRequest,
    uow: UowDep,
    tenant_uow: TenantUowDep,
    outbox: OutboxDep,
    cache: CacheDep,
) -> ApiResponse[PermissionItem]:
    """更新权限码（组合不可换绑，仅状态）。

    Args:
        permission_id: 权限码主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为权限码行。
    """
    await _service(uow, outbox, cache, tenant_uow).update_permission(permission_id, req)
    return ApiResponse.ok(await _permission_item(uow, outbox, cache, permission_id))


@permission_router.delete("/{permission_id}", dependencies=[_REQUIRE_PERMISSION_MANAGE])
async def delete_permission(
    permission_id: int, uow: UowDep, tenant_uow: TenantUowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[None]:
    """删除权限码（有条件删除）。

    Args:
        permission_id: 权限码主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache, tenant_uow).delete_permission(permission_id)
    return ApiResponse.ok(None)


async def _business_item(
    uow: UnitOfWork, outbox: BaseOutboxStore, cache: CacheRegion, business_id: int
) -> BusinessItem:
    """取单个业务码行（复用列表装配，含权限码数与多语言映射）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        business_id: 业务码主键。

    Returns:
        BusinessItem: 业务码行。

    Raises:
        MenuNotFoundError: 业务码不存在（40201）。
    """
    for item in (await _service(uow, outbox, cache).list_businesses()).items:
        if item.id == business_id:
            return item
    raise MenuNotFoundError(f"业务码不存在：{business_id}")  # pragma: no cover - 更新前已校验存在


async def _action_item(uow: UnitOfWork, outbox: BaseOutboxStore, cache: CacheRegion, action_id: int) -> ActionItem:
    """取单个动作码行。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        action_id: 动作码主键。

    Returns:
        ActionItem: 动作码行。

    Raises:
        MenuNotFoundError: 动作码不存在（40201）。
    """
    for item in (await _service(uow, outbox, cache).list_actions()).items:
        if item.id == action_id:
            return item
    raise MenuNotFoundError(f"动作码不存在：{action_id}")  # pragma: no cover - 更新前已校验存在


async def _permission_item(
    uow: UnitOfWork, outbox: BaseOutboxStore, cache: CacheRegion, permission_id: int
) -> PermissionItem:
    """取单个权限码行（复用列表装配，含派生名称）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        permission_id: 权限码主键。

    Returns:
        PermissionItem: 权限码行。

    Raises:
        MenuNotFoundError: 权限码不存在（40201）。
    """
    for item in (await _service(uow, outbox, cache).list_permissions(None)).items:
        if item.id == permission_id:
            return item
    raise MenuNotFoundError(f"权限码不存在：{permission_id}")  # pragma: no cover - 更新前已校验存在
