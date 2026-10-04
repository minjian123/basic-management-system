"""平台服务菜单与权限元数据端点（`/api/v1/menus`、`/forms`、`/buttons`、`/fields`、`/businesses`、`/actions`）。

- **鉴权**：模块级 `require_auth`；读挂 `menu:query` / `business:query` / `action:query`，
  写挂 `menu:create` / `menu:update` / `menu:delete`（当前 `NullPermissionChecker` 恒放行，
  `02_04` 注入真实权限检查器后自动收口，路由声明无需回改）；
- **库**：菜单元数据落**平台服务库**（`platform:platform` 链），故取 `get_platform_uow`（固定平台库主库）；
  带租户上下文的 `get_uow` 会按请求租户库选引擎、误连租户库；
- **契约**：计入 platform 公开契约（`deploy/contracts/platform.json`）；新增端点属非破坏性变更；
- **动态菜单**：`GET /api/v1/menus/my` 登录即可访问，按当前用户权限过滤菜单树并下发表单元数据。
"""

from datetime import datetime
from typing import Annotated, cast

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
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.base import DEFAULT_LOCALE, SUPPORTED_LOCALES
from bms_core.menu import DEFAULT_MENU_TREE_CACHE_TTL, MENU_TREE_CACHE_TTL_KEY
from bms_core.outbox.base import BaseOutboxStore
from bms_core.permission.base import BasePermissionChecker, require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.models.menu import SysButton, SysField, SysForm, SysMenu
from bms_platform.repositories.menu import (
    ActionRepository,
    BusinessRepository,
    ButtonRepository,
    FieldRepository,
    FormRepository,
    MenuRepository,
)
from bms_platform.schemas.menu import (
    ActionList,
    BusinessList,
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
from bms_platform.services.menu import MenuMetadataService
from bms_platform.services.my_menu import MyMenuService

menu_router = BaseRouter(
    key="sys_menus",
    prefix="/menus",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)
form_router = BaseRouter(
    key="sys_forms",
    prefix="/forms",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)
button_router = BaseRouter(
    key="sys_buttons",
    prefix="/buttons",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)
field_router = BaseRouter(
    key="sys_fields",
    prefix="/fields",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)
business_router = BaseRouter(
    key="sys_businesses",
    prefix="/businesses",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)
action_router = BaseRouter(
    key="sys_actions",
    prefix="/actions",
    tags=["menu"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
ConfigDep = Annotated[BaseConfigSource, Depends(get_config_source)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]

MenuIdQuery = Annotated[int | None, Query(gt=0, description="菜单主键（可空 = 全部）")]
FormIdQuery = Annotated[int | None, Query(gt=0, description="表单主键（可空 = 全部）")]
BusinessIdQuery = Annotated[int | None, Query(gt=0, description="业务码主键（可空 = 全部）")]

_REQUIRE_MENU_QUERY = Depends(require_permission("menu:query"))
_REQUIRE_MENU_CREATE = Depends(require_permission("menu:create"))
_REQUIRE_MENU_UPDATE = Depends(require_permission("menu:update"))
_REQUIRE_MENU_DELETE = Depends(require_permission("menu:delete"))
_REQUIRE_BUSINESS_QUERY = Depends(require_permission("business:query"))
_REQUIRE_ACTION_QUERY = Depends(require_permission("action:query"))


def _service(uow: UnitOfWork, outbox: BaseOutboxStore, cache: CacheRegion) -> MenuMetadataService:
    """构造元数据服务（请求级会话）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        MenuMetadataService: 元数据服务实例。
    """
    session = cast("DbSession", uow.session)
    return MenuMetadataService(
        uow=uow,
        businesses=BusinessRepository(session),
        actions=ActionRepository(session),
        menus=MenuRepository(session),
        forms=FormRepository(session),
        buttons=ButtonRepository(session),
        fields=FieldRepository(session),
        outbox=outbox,
        cache=cache,
    )


def _accept_locale(request: Request) -> str:
    """解析 `Accept-Language`（支持清单内匹配；缺省默认语言）。

    Args:
        request: 请求对象。

    Returns:
        str: 生效语言。
    """
    raw = request.headers.get("accept-language", "")
    for part in raw.split(","):
        tag = part.split(";")[0].strip()
        if not tag:
            continue
        if tag in SUPPORTED_LOCALES:
            return tag
        prefix = tag.split("-")[0].lower()
        for supported in SUPPORTED_LOCALES:
            if supported.split("-")[0].lower() == prefix:
                return supported
    return DEFAULT_LOCALE


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


def _menu_item(row: SysMenu) -> MenuItem:
    """菜单记录 → 契约行。

    Args:
        row: 菜单记录。

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
        i18n=ConcurrentStableDict(),
    )


def _form_item(row: SysForm) -> FormItem:
    """表单记录 → 契约行。

    Args:
        row: 表单记录。

    Returns:
        FormItem: 表单契约行。
    """
    return FormItem(
        id=row.id,
        menu_id=row.menu_id,
        business_id=row.business_id,
        component=row.component,
        status=row.status,
        created_at=cast("datetime", row.created_at),
        updated_at=cast("datetime", row.updated_at),
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
        action_id=row.action_id,
        name=row.name,
        type=row.type,
        sort=row.sort,
        status=row.status,
    )


def _field_item(row: SysField) -> FieldItem:
    """字段记录 → 契约行。

    Args:
        row: 字段记录。

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
        i18n=ConcurrentStableDict(),
    )


# ------------------------------------------------------------------ 动态菜单（登录即可）


@menu_router.get("/my")
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
    locale = _accept_locale(request)
    ttl = await _tree_ttl(config)
    service = MyMenuService(metadata=_service(uow, outbox, cache), checker=checker)
    return ApiResponse.ok(await service.build(locale=locale, tenant_id=current_tenant_id_str(), ttl=ttl))


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
    return ApiResponse.ok(_menu_item(await _service(uow, outbox, cache).create_menu(req)))


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
    return ApiResponse.ok(_menu_item(await _service(uow, outbox, cache).update_menu(menu_id, req)))


@menu_router.delete("/{menu_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_menu(menu_id: int, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[None]:
    """删除菜单（软删除）。

    Args:
        menu_id: 菜单主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache).delete_menu(menu_id)
    return ApiResponse.ok(None)


# ------------------------------------------------------------------ 表单维护


@form_router.get("", dependencies=[_REQUIRE_MENU_QUERY])
async def list_forms(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, menu_id: MenuIdQuery = None
) -> ApiResponse[FormList]:
    """表单清单（按菜单过滤）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        menu_id: 菜单主键（可空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为表单清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_forms(menu_id))


@form_router.post("", dependencies=[_REQUIRE_MENU_CREATE])
async def create_form(req: FormCreateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[FormItem]:
    """新增表单（菜单 1:1 / 业务 1:1）。

    Args:
        req: 新增请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为表单行。
    """
    row = await _service(uow, outbox, cache).create_form(
        menu_id=req.menu_id, business_id=req.business_id, component=req.component, status=req.status
    )
    return ApiResponse.ok(_form_item(row))


@form_router.put("/{form_id}", dependencies=[_REQUIRE_MENU_UPDATE])
async def update_form(
    form_id: int, req: FormUpdateRequest, uow: UowDep, outbox: OutboxDep, cache: CacheDep
) -> ApiResponse[FormItem]:
    """更新表单。

    Args:
        form_id: 表单主键。
        req: 更新请求。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应，data 为更新后的表单行。
    """
    row = await _service(uow, outbox, cache).update_form(
        form_id, business_id=req.business_id, component=req.component, status=req.status
    )
    return ApiResponse.ok(_form_item(row))


@form_router.delete("/{form_id}", dependencies=[_REQUIRE_MENU_DELETE])
async def delete_form(form_id: int, uow: UowDep, outbox: OutboxDep, cache: CacheDep) -> ApiResponse[None]:
    """删除表单（软删除）。

    Args:
        form_id: 表单主键。
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。

    Returns:
        ApiResponse: 统一响应（data 为空）。
    """
    await _service(uow, outbox, cache).delete_form(form_id)
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
        action_id=req.action_id,
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
        action_id=req.action_id,
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
    row = await _service(uow, outbox, cache).create_field(
        form_id=req.form_id,
        field_key=req.field_key,
        name=req.name,
        type=req.type,
        sort=req.sort,
        status=req.status,
        i18n=req.i18n,
    )
    return ApiResponse.ok(_field_item(row))


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
    row = await _service(uow, outbox, cache).update_field(
        field_id, name=req.name, type=req.type, sort=req.sort, status=req.status, i18n=req.i18n
    )
    return ApiResponse.ok(_field_item(row))


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
async def list_actions(
    uow: UowDep, outbox: OutboxDep, cache: CacheDep, business_id: BusinessIdQuery = None
) -> ApiResponse[ActionList]:
    """动作权限码清单（租户侧可见、只读）。

    Args:
        uow: 请求级工作单元。
        outbox: 发件箱存储。
        cache: 缓存 Region。
        business_id: 业务码主键（可空 = 全部）。

    Returns:
        ApiResponse: 统一响应，data 为动作码清单。
    """
    return ApiResponse.ok(await _service(uow, outbox, cache).list_actions(business_id))
