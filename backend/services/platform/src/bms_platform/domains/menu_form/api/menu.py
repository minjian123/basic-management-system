"""平台服务菜单与权限元数据端点（`/api/v1/menus`、`/forms`、`/buttons`、`/fields`、`/businesses`、`/actions`）。

- **鉴权**：模块级 `require_auth`；读挂 `menu:query` / `business:query` / `action:query`，
  写挂 `menu:create` / `menu:update` / `menu:delete`（当前 `NullPermissionChecker` 恒放行，
  `02_04` 注入真实权限检查器后自动收口，路由声明无需回改）；
- **库**：菜单元数据落**平台服务库**（`platform:platform` 链），故取 `get_platform_uow`（固定平台库主库）；
  带租户上下文的 `get_uow` 会按请求租户库选引擎、误连租户库；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更；
- **动态菜单**：`GET /api/v1/menus/my` 登录即可访问，按当前用户权限过滤菜单树并下发表单元数据。
"""

from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import (
    get_cache_region,
    get_config_source,
    get_outbox_store,
    get_permission_checker,
    get_platform_uow,
)
from bms_core.cache.base import CacheRegion
from bms_core.config.base import BaseConfigSource
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_tenant
from bms_core.db.session import get_uow as get_tenant_uow
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.menu import DEFAULT_MENU_TREE_CACHE_TTL, MENU_TREE_CACHE_TTL_KEY
from bms_core.models.platform.menu_form import SysButton, SysField, SysForm, SysMenu
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import BasePermissionChecker, prepare_permission_dependency, require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.services.module_registry import TENANT_OPTIONAL_MODULE_KEYS
from bms_core.tenant_module.base import get_tenant_module_gate
from bms_platform.api.locale import accept_locale, locale_scope
from bms_platform.domains.menu_form.schemas.menu import (
    ButtonCreateRequest,
    ButtonItem,
    ButtonList,
    ButtonUpdateRequest,
    FieldCreateRequest,
    FieldItem,
    FieldList,
    FieldUpdateRequest,
    FormCreateRequest,
    FormItem,
    FormList,
    FormUpdateRequest,
    MenuCreateRequest,
    MenuItem,
    MenuTree,
    MenuUpdateRequest,
    MyMenuResponse,
)
from bms_platform.domains.menu_form.services.menu import MenuFormService
from bms_platform.domains.menu_form.services.my_menu import MyMenuService
from bms_platform.wiring import build_menu_service

menu_router = BaseRouter(
    key="sys_menus",
    prefix="/menus",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)
form_router = BaseRouter(
    key="sys_forms",
    prefix="/forms",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)
button_router = BaseRouter(
    key="sys_buttons",
    prefix="/buttons",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)
field_router = BaseRouter(
    key="sys_fields",
    prefix="/fields",
    tags=["menu"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
TenantUowDep = Annotated[UnitOfWork, Depends(get_tenant_uow)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]

MenuIdQuery = Annotated[int | None, Query(gt=0, description="菜单主键（可空 = 全部）")]
FormIdQuery = Annotated[int | None, Query(gt=0, description="表单主键（可空 = 全部）")]

_REQUIRE_MENU_QUERY = Depends(require_permission("menu:query"))
_REQUIRE_MENU_CREATE = Depends(require_permission("menu:create"))
_REQUIRE_MENU_UPDATE = Depends(require_permission("menu:update"))
_REQUIRE_MENU_DELETE = Depends(require_permission("menu:delete"))


def _service(
    uow: UnitOfWork,
    outbox: BaseOutboxStore,
    cache: CacheRegion,
    tenant_uow: UnitOfWork | None = None,
) -> MenuFormService:
    """构造菜单表单服务（请求级会话）。

    Args:
        uow: 请求级工作单元（平台库：菜单 / 表单 / 字典表）。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        tenant_uow: 租户库工作单元（角色授权引用探测；缺省不探测）。

    Returns:
        MenuFormService: 菜单表单服务实例。
    """
    return build_menu_service(
        uow=uow,
        outbox=outbox,
        cache=cache,
        tenant_session=tenant_uow.session if tenant_uow is not None else None,
    )


async def _tree_ttl(config: BaseConfigSource) -> int:
    """取菜单树缓存 TTL（`sys_config` 参数，缺省 300 秒）。

    Args:
        config: 系统参数读取基座。

    Returns:
        int: 缓存有效期（秒，最小 1）。
    """
    raw = await config.get(MENU_TREE_CACHE_TTL_KEY, str(DEFAULT_MENU_TREE_CACHE_TTL))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MENU_TREE_CACHE_TTL
    return max(1, value)


def _menu_item(row: SysMenu, i18n: ConcurrentStableDict[str, str]) -> MenuItem:
    """菜单记录 → 契约行（出参含完整多语言映射）。

    Args:
        row: 菜单记录。
        i18n: 该菜单的多语言文案映射（含必填语言回填）。

    Returns:
        MenuItem: 菜单契约行。
    """
    return MenuItem(
        id=row.id,
        parent_id=row.parent_id,
        name=row.name,
        path=row.path,
        component=row.component,
        icon=row.icon,
        sort=row.sort,
        hidden=row.hidden,
        status=row.status,
        i18n=i18n,
    )


def _menu_id_strings(menu_ids: ConcurrentStableList[int]) -> ConcurrentStableList[str]:
    """菜单入口 ID 清单字符串化（雪花 ID 防 JS 精度丢失）。

    Args:
        menu_ids: 请求中的菜单入口 ID 清单（整型）。

    Returns:
        ConcurrentStableList[str]: 字符串化 ID 清单。
    """
    return ConcurrentStableList(str(item) for item in menu_ids)


def _form_item(row: SysForm, menu_ids: ConcurrentStableList[str]) -> FormItem:
    """表单记录 → 契约行。

    Args:
        row: 表单记录。
        menu_ids: 关联菜单入口 ID 清单。

    Returns:
        FormItem: 表单契约行。
    """
    return FormItem(
        id=row.id,
        menu_ids=menu_ids,
        business_id=row.business_id,
        component=row.component,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _button_item(row: SysButton) -> ButtonItem:
    """按钮记录 → 契约行。

    Args:
        row: 按钮记录。

    Returns:
        ButtonItem: 按钮契约行。
    """
    return ButtonItem(
        id=row.id,
        form_id=row.form_id,
        permission_id=row.permission_id,
        name=row.name,
        type=row.type,
        sort=row.sort,
        status=row.status,
    )


def _field_item(row: SysField, i18n: ConcurrentStableDict[str, str]) -> FieldItem:
    """字段记录 → 契约行（出参含完整多语言映射）。

    Args:
        row: 字段记录。
        i18n: 该字段的多语言文案映射（含必填语言回填）。

    Returns:
        FieldItem: 字段契约行。
    """
    return FieldItem(
        id=row.id,
        form_id=row.form_id,
        field_key=row.field_key,
        name=row.name,
        type=row.type,
        sort=row.sort,
        status=row.status,
        i18n=i18n,
    )


# ------------------------------------------------------------------ 动态菜单（登录即可）


@menu_router.get("/my", dependencies=[Depends(prepare_permission_dependency())])
async def my_menus(
    request: Request,
    uow: UowDep,
    outbox: OutboxDep,
    cache: CacheDep,
    config: ConfigDep,
    checker: CheckerDep,
) -> ApiResponse[MyMenuResponse]:
    """当前用户动态菜单树 + 表单元数据 + 权限码集合。

    Args:
        request: 请求对象（解析语言）。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        config: 系统参数读取基座（缓存 TTL）。
        checker: 权限检查器。

    Returns:
        ApiResponse: 统一响应，data 为动态菜单。
    """
    locale = accept_locale(request)
    ttl = await _tree_ttl(config)
    service = MyMenuService(metadata=_service(uow, outbox, cache), checker=checker)
    return ApiResponse.ok(
        await service.build(
            locale=locale,
            tenant_id=current_tenant_id_str(),
            ttl=ttl,
            module_states=await _module_states(request),
        )
    )


async def _module_states(request: Request) -> ConcurrentStableDict[str, str]:
    """取当前租户的可勾选模块状态（模块停用 / 未开通即隐藏对应菜单）。

    Args:
        request: 请求对象（取门禁实现）。

    Returns:
        ConcurrentStableDict[str, str]: 模块标识 → 状态（无租户上下为空）。
    """
    tenant_key = current_tenant_id_str()
    if not tenant_key or not tenant_key.isdigit():
        return ConcurrentStableDict()
    gate = get_tenant_module_gate(request)
    states: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    for module_key in sorted(TENANT_OPTIONAL_MODULE_KEYS):
        states.set(
            module_key,
            await gate.state(tenant_id=int(tenant_key), tenant_code=current_tenant.get(), module_key=module_key),
        )
    return states


# ------------------------------------------------------------------ 菜单维护


@menu_router.get("", dependencies=[_REQUIRE_MENU_QUERY])
async def list_menus(uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[MenuTree]:
    """菜单树（平台维护视图，含 hidden 与 disabled）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为菜单树。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_menu_tree())


@menu_router.post("", dependencies=[_REQUIRE_MENU_CREATE])
async def create_menu(req: MenuCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[MenuItem]:
    """新增菜单。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为菜单行。
    """
    row, i18n = await _service(uow, outbox, cache).create_menu(req)
    return ApiResponse.ok(_menu_item(row, i18n))


@menu_router.put("/{menu_id}", dependencies=[_REQUIRE_MENU_UPDATE])
async def update_menu(
    menu_id: int, req: MenuUpdateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[MenuItem]:
    """更新菜单。

    Args:
        menu_id: 菜单主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为更新后的菜单行。
    """
    row, i18n = await _service(uow, outbox, cache).update_menu(menu_id, req)
    return ApiResponse.ok(_menu_item(row, i18n))


@menu_router.delete("/{menu_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_menu(
    menu_id: int, uow: UowDep, tenant_uow: TenantUowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[None]:
    """删除菜单（软删除）。

    Args:
        menu_id: 菜单主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache, tenant_uow).delete_menu(menu_id)
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 表单维护


@form_router.get("", dependencies=[_REQUIRE_MENU_QUERY])
async def list_forms(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, menu_id: MenuIdQuery = None
) -> ApiResponse[FormList]:
    """表单清单（`menu_id` 非空时按菜单关联过滤；可空 = 全量，含无入口表单）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        menu_id: 菜单主键（可空 = 全量）。

    Returns:
        ApiResponse: 统一响应，data 为表单清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_forms(menu_id))


@form_router.post("", dependencies=[_REQUIRE_MENU_CREATE])
async def create_form(req: FormCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[FormItem]:
    """新增表单（业务 1:1；菜单入口多对多）。

    Args:
        req: 新增请求（关联菜单入口清单 / 业务码 / 组件 / 状态）。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为表单行。
    """
    row = await _service(uow, outbox, cache).create_form(
        menu_ids=req.menu_ids, business_id=req.business_id, component=req.component, status=req.status
    )
    return ApiResponse.ok(_form_item(row, _menu_id_strings(req.menu_ids)))


@form_router.put("/{form_id}", dependencies=[_REQUIRE_MENU_UPDATE])
async def update_form(
    form_id: int, req: FormUpdateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[FormItem]:
    """更新表单（菜单入口关联全量替换）。

    Args:
        form_id: 表单主键。
        req: 更新请求（关联菜单入口清单 / 业务码 / 组件 / 状态）。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为更新后的表单行。
    """
    row = await _service(uow, outbox, cache).update_form(
        form_id, menu_ids=req.menu_ids, business_id=req.business_id, component=req.component, status=req.status
    )
    return ApiResponse.ok(_form_item(row, _menu_id_strings(req.menu_ids)))


@form_router.delete("/{form_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_form(
    form_id: int, uow: UowDep, tenant_uow: TenantUowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[None]:
    """删除表单（软删除）。

    Args:
        form_id: 表单主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache, tenant_uow).delete_form(form_id)
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 按钮维护


@button_router.get("", dependencies=[_REQUIRE_MENU_QUERY])
async def list_buttons(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, form_id: FormIdQuery = None
) -> ApiResponse[ButtonList]:
    """按钮清单（按表单过滤）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        form_id: 表单主键（可空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为按钮清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_buttons(form_id))


@button_router.post("", dependencies=[_REQUIRE_MENU_CREATE])
async def create_button(
    req: ButtonCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[ButtonItem]:
    """新增按钮（表单 + 动作 1:1）。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为按钮行。
    """
    row = await _service(uow, outbox, cache).create_button(
        form_id=req.form_id,
        permission_id=req.permission_id,
        name=req.name,
        type=req.type,
        sort=req.sort,
        status=req.status,
    )
    return ApiResponse.ok(_button_item(row))


@button_router.put("/{button_id}", dependencies=[_REQUIRE_MENU_UPDATE])
async def update_button(
    button_id: int, req: ButtonUpdateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[ButtonItem]:
    """更新按钮。

    Args:
        button_id: 按钮主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为更新后的按钮行。
    """
    row = await _service(uow, outbox, cache).update_button(
        button_id,
        permission_id=req.permission_id,
        name=req.name,
        type=req.type,
        sort=req.sort,
        status=req.status,
    )
    return ApiResponse.ok(_button_item(row))


@button_router.delete("/{button_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_button(button_id: int, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[None]:
    """删除按钮（软删除）。

    Args:
        button_id: 按钮主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache).delete_button(button_id)
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 字段维护


@field_router.get("", dependencies=[_REQUIRE_MENU_QUERY])
async def list_fields(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, form_id: FormIdQuery = None
) -> ApiResponse[FieldList]:
    """字段清单（按表单过滤）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        form_id: 表单主键（可空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为字段清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_fields(form_id))


@field_router.post("", dependencies=[_REQUIRE_MENU_CREATE])
async def create_field(
    req: FieldCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[FieldItem]:
    """新增字段（表单内字段键唯一）。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为字段行。
    """
    row, i18n = await _service(uow, outbox, cache).create_field(
        form_id=req.form_id,
        field_key=req.field_key,
        type=req.type,
        sort=req.sort,
        status=req.status,
        i18n=req.i18n,
    )
    return ApiResponse.ok(_field_item(row, i18n))


@field_router.put("/{field_id}", dependencies=[_REQUIRE_MENU_UPDATE])
async def update_field(
    field_id: int, req: FieldUpdateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[FieldItem]:
    """更新字段。

    Args:
        field_id: 字段主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为更新后的字段行。
    """
    row, i18n = await _service(uow, outbox, cache).update_field(
        field_id, type=req.type, sort=req.sort, status=req.status, i18n=req.i18n
    )
    return ApiResponse.ok(_field_item(row, i18n))


@field_router.delete("/{field_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_field(field_id: int, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[None]:
    """删除字段（软删除）。

    Args:
        field_id: 字段主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache).delete_field(field_id)
    return ApiResponse.ok(None)
