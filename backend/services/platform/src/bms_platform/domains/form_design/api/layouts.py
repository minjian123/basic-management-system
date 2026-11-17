"""布局与字段属性管理端点：`/api/v1/form-design/layouts` / `/api/v1/form-design/attrs`（10_01）。

- **鉴权**：模块级 `require_auth`；写端点 `formdesign:manage`、读端点 `formdesign:query`；
- **整份覆盖**：保存即该层级全量（布局 = 一份配置，属性 = 字段清单）；
- **恢复默认**：DELETE 删当前层级 → 自然回退下一级（角色 → 租户 → 平台 → 空布局）；
- **平台默认层级**：`scope=platform` 写操作要求平台超管（`platform_admin` 角色）。
"""

from typing import Annotated, cast

from fastapi import Depends, Query, Request
from starlette.applications import Starlette

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_cache_region,
    get_distributed_lock,
    get_option_set_registry,
    get_outbox_store,
    get_platform_uow,
    get_uow,
)
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import get_current_user_id
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.lock.base import BaseDistributedLock
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import require_permission
from bms_core.registry.forms import FormRegistry
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.form_design.schemas.layout import (
    FieldAttrRow,
    FieldAttrSaveRequest,
    LayoutLevelRow,
    LayoutListResponse,
    LayoutSaveRequest,
    LayoutSaveResult,
)
from bms_platform.domains.form_design.services.layout import FormDesignService
from bms_platform.wiring import build_form_design_service


def _root_app(request: Request) -> Starlette:
    r"""取根应用（\`request.app\` 在子路由挂载下可能是内层应用；\`scope["app"]\` 才是根）。

    Args:
        request: 请求对象。

    Returns:
        Starlette: 根应用（含 \`state\`）。
    """
    return cast("Starlette", request.scope.get("app") or request.app)


__all__ = ["router"]

router = BaseRouter(
    key="form_design_layout",
    prefix="/form-design",
    tags=["form-design"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("formdesign:query"))
_REQUIRE_MANAGE = Depends(require_permission("formdesign:manage"))

FormCodeQuery = Annotated[str, Query(min_length=1, max_length=64, description="表单标识（业务码）")]


def _service(
    request: Request,
    tenant_uow: Annotated[UnitOfWork, Depends(get_uow)],
    platform_uow: Annotated[UnitOfWork, Depends(get_platform_uow)],
    cache: Annotated[CacheRegion, Depends(get_cache_region)],
    outbox: Annotated[BaseOutboxStore, Depends(get_outbox_store)],
    lock: Annotated[BaseDistributedLock, Depends(get_distributed_lock)],
    option_sets: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
) -> FormDesignService:
    """构造请求级表单定制服务（租户库 + 平台库双会话，装配面统一构造）。

    Args:
        tenant_uow: 租户库工作单元（布局 / 属性 / 自建字段）。
        platform_uow: 平台库工作单元（只读元数据）。
        cache: 缓存 Region。
        outbox: 事务性发件箱。
        lock: 分布式锁（DDL 单租户串行）。
        option_sets: 选项集注册表。

    Returns:
        FormDesignService: 服务实例。
    """
    return build_form_design_service(
        tenant_uow=tenant_uow,
        platform_uow=platform_uow,
        cache=cache,
        outbox=outbox,
        lock=lock,
        option_set_registry=option_sets,
        registry=cast("FormRegistry", _root_app(request).state.form_registry),
    )


ServiceDep = Annotated[FormDesignService, Depends(_service)]


@router.get("/layouts", dependencies=[_REQUIRE_QUERY])
async def list_layouts(service: ServiceDep, form_code: FormCodeQuery) -> ApiResponse[LayoutListResponse]:
    """取该表单的三层布局 + 三层属性。

    需要 `formdesign:query`；业务码不存在或不可定制返回 `40401`。

    Args:
        service: 表单定制服务。
        form_code: 表单标识（业务码）。

    Returns:
        ApiResponse[LayoutListResponse]: 统一响应，data 为布局 / 属性清单与已配置层级。
    """
    layouts, attrs, _ext_rows = await service.list_levels(form_code)
    layout_rows: ConcurrentStableList[LayoutLevelRow] = ConcurrentStableList()
    for row in layouts:
        layout_rows.add(
            LayoutLevelRow(
                id=row.id,
                form_code=row.form_code,
                scope=row.scope,
                role_id=row.role_id,
                layout_config=service.layout_config_of(row),
                status=row.status,
            )
        )
    attr_rows: ConcurrentStableList[FieldAttrRow] = ConcurrentStableList()
    for row in attrs:
        attr_rows.add(
            FieldAttrRow(
                id=row.id,
                form_code=row.form_code,
                scope=row.scope,
                role_id=row.role_id,
                field_key=row.field_key,
                attrs=service.attrs_of(row),
            )
        )
    levels: ConcurrentStableList[str] = ConcurrentStableList()
    for row in layouts:
        if row.scope not in levels:
            levels.add(row.scope)
    return ApiResponse.ok(
        LayoutListResponse(
            layouts=layout_rows,
            attrs=attr_rows,
            warnings=ConcurrentStableList(),
            levels=levels,
        )
    )


@router.put("/layouts", dependencies=[_REQUIRE_MANAGE])
async def save_layout(
    request: Request,
    service: ServiceDep,
    payload: LayoutSaveRequest,
) -> ApiResponse[LayoutSaveResult]:
    """保存某层级布局（整份覆盖式）。

    需要 `formdesign:manage`；`scope=platform` 要求平台超管；布局结构非法返回 `40403`。

    Args:
        request: 请求对象（取角色集）。
        service: 表单定制服务。
        payload: 保存请求。

    Returns:
        ApiResponse[LayoutSaveResult]: 统一响应，data 为写入结果。
    """
    row = await service.save_layout(
        form_code=payload.form_code,
        scope=payload.scope,
        role_id=payload.role_id,
        layout_config=payload.layout_config,
        require_platform_admin=payload.scope == "platform",
        user_id=get_current_user_id(),
    )
    return ApiResponse.ok(
        LayoutSaveResult(
            id=row.id,
            scope=row.scope,
            role_id=row.role_id,
            applied=True,
            warnings=ConcurrentStableList(),
        )
    )


@router.delete("/layouts/{layout_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_layout(request: Request, service: ServiceDep, layout_id: str) -> ApiResponse[LayoutSaveResult]:
    """删除某层级布局（恢复默认：回退下一级）。

    需要 `formdesign:manage`。主键不存在返回 `10002`。

    Args:
        request: 请求对象（取角色集）。
        service: 表单定制服务。
        layout_id: 布局主键（字符串化雪花 ID）。

    Returns:
        ApiResponse[LayoutSaveResult]: 统一响应，data 为删除结果。
    """
    from bms_core.core.exceptions import NotFoundError, ParamError

    if not layout_id.isdigit():
        raise ParamError(f"布局主键非法：{layout_id}")
    deleted = await service.delete_layout_by_id(
        int(layout_id),
        require_platform_admin_check=True,
        user_id=get_current_user_id(),
    )
    if deleted is None:
        raise NotFoundError(f"布局不存在：{layout_id}")
    row, removed = deleted
    return ApiResponse.ok(
        LayoutSaveResult(
            id=row.id,
            scope=row.scope,
            role_id=row.role_id,
            applied=removed,
            warnings=ConcurrentStableList(),
        )
    )


@router.put("/attrs", dependencies=[_REQUIRE_MANAGE])
async def save_attrs(
    request: Request,
    service: ServiceDep,
    payload: FieldAttrSaveRequest,
) -> ApiResponse[LayoutSaveResult]:
    """保存某层级字段属性（整份覆盖式）。

    需要 `formdesign:manage`；`scope=platform` 要求平台超管；属性非法返回 `40408`。

    Args:
        request: 请求对象（取角色集）。
        service: 表单定制服务。
        payload: 保存请求。

    Returns:
        ApiResponse[LayoutSaveResult]: 统一响应，data 为写入结果。
    """
    items: ConcurrentStableList[tuple[str, object, str]] = ConcurrentStableList()
    for item in payload.fields:
        items.add((item.field_key, item.attrs, item.field_type))
    rows = await service.save_attrs(
        form_code=payload.form_code,
        scope=payload.scope,
        role_id=payload.role_id,
        items=items,
        require_platform_admin=payload.scope == "platform",
        user_id=get_current_user_id(),
    )
    first_id = rows[0].id if len(rows) > 0 else 0
    return ApiResponse.ok(
        LayoutSaveResult(
            id=first_id,
            scope=payload.scope,
            role_id=payload.role_id,
            applied=True,
            warnings=ConcurrentStableList(),
        )
    )


@router.delete("/attrs/{attr_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_attrs(request: Request, service: ServiceDep, attr_id: str) -> ApiResponse[LayoutSaveResult]:
    """删除某层级的全部属性（恢复默认）。

    需要 `formdesign:manage`。主键不存在返回 `10002`。

    Args:
        request: 请求对象（取角色集）。
        service: 表单定制服务。
        attr_id: 属性主键（字符串化雪花 ID）。

    Returns:
        ApiResponse[LayoutSaveResult]: 统一响应，data 为删除结果。
    """
    from bms_core.core.exceptions import NotFoundError, ParamError

    if not attr_id.isdigit():
        raise ParamError(f"属性主键非法：{attr_id}")
    deleted = await service.delete_attrs_by_id(
        int(attr_id),
        require_platform_admin_check=True,
        user_id=get_current_user_id(),
    )
    if deleted is None:
        raise NotFoundError(f"属性不存在：{attr_id}")
    row, removed = deleted
    return ApiResponse.ok(
        LayoutSaveResult(
            id=row.id,
            scope=row.scope,
            role_id=row.role_id,
            applied=removed,
            warnings=ConcurrentStableList(),
        )
    )
