"""api 层接口路由基座：统一模块路由基类、路由登记与统一挂载、参数绑定与鉴权依赖占位。

- `API_PREFIX`：内部接口统一前缀（`/api/v1`）；`main.py` 不再重复传前缀。
- `DEFAULT_RESPONSES`：统一错误响应文档（401 / 403 / 404 / 429 / 500 → `ApiResponse` 形态），
  作为路由默认 `responses` 进 OpenAPI 契约。
- `BaseRouter`：模块（能力域）路由基类（继承 FastAPI `APIRouter` + `BaseObject`）——统一前缀 /
  tags / 默认错误响应 / 元信息；模块路由一律继承它，不得裸建 `APIRouter`。
- `RouterRegistry` / `register_router` / `build_api_router`：路由登记（`key` 唯一拒重）与统一挂载。
- `page_query` / `sort_query` / `cursor_query`：分页 / 排序 / 游标参数统一 `Depends` 绑定工厂
  （复用 `BasePageQuery` / `BaseSortQuery` / `BaseCursorQuery`）。
- `require_auth`：登录态依赖占位（恒定放行，**不解析 token**）；真实登录态与权限校验随
  认证 / RBAC 阶段（权限码校验沿用 `require_permission`）。
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Query, params
from pydantic import ValidationError

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import ConflictError, ParamError
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BaseCursorQuery, BasePageQuery
from bms_core.schemas.sorting import BaseSortQuery

__all__ = [
    "API_PREFIX",
    "DEFAULT_RESPONSES",
    "BaseRouter",
    "RouterRegistry",
    "build_api_router",
    "cursor_query",
    "mount_service_routers",
    "page_query",
    "register_router",
    "require_auth",
    "router_registry",
    "sort_query",
]

API_PREFIX = "/api/v1"
"""内部接口统一前缀（管理端 / 租户端全部接口；开放接口 `/api/open` 独立，见《API接口规范》）。"""

DEFAULT_RESPONSES: Mapping[int, dict[str, object]] = {
    401: {"model": ApiResponse, "description": "未认证"},
    403: {"model": ApiResponse, "description": "无权限"},
    404: {"model": ApiResponse, "description": "资源不存在"},
    429: {"model": ApiResponse, "description": "限流"},
    500: {"model": ApiResponse, "description": "服务异常"},
}
"""统一错误响应文档（HTTP 状态码 → OpenAPI 响应描述；业务失败统一 200 + 业务码）。"""


class BaseRouter(APIRouter, BaseObject):
    """统一模块路由基类：前缀 / tags / 默认错误响应 / 元信息（模块路由一律继承它）。

    - `key`：路由模块唯一标识（登记表以 `key` 拒重）。
    - `default_responses`：是否合并 `DEFAULT_RESPONSES`（探针等豁免统一响应的路由置 False）。
    """

    key: str = "router"
    """路由模块唯一标识（如 `demo` / `modules` / `plugins` / `health`）。"""

    default_responses: bool = True
    """是否合并 `DEFAULT_RESPONSES`（默认 True；探针路由置 False）。"""

    def __init__(
        self,
        *,
        key: str = "",
        prefix: str = "",
        tags: Sequence[str] = (),
        dependencies: Sequence[params.Depends] | None = None,
        responses: Mapping[int | str, dict[str, object]] | None = None,
        default_responses: bool | None = None,
        **kwargs: Any,
    ) -> None:
        """构造模块路由。

        Args:
            key: 路由模块标识；缺省取类属性 `key`。
            prefix: 路由前缀（相对统一挂载前缀）。
            tags: OpenAPI 分组标签。
            dependencies: 路由级依赖（如 `Depends(require_auth)`）。
            responses: 附加 / 覆盖的错误响应文档（同名状态码覆盖默认）。
            default_responses: 是否合并 `DEFAULT_RESPONSES`；None 取类属性。
            **kwargs: 透传 `APIRouter` 其余参数。
        """
        self.key = key or type(self).key
        if default_responses is not None:
            self.default_responses = default_responses
        merged: dict[int | str, dict[str, object]] = dict(responses or {})
        if self.default_responses:
            merged = {**DEFAULT_RESPONSES, **merged}
        super().__init__(
            prefix=prefix,
            tags=list(tags) or None,
            dependencies=list(dependencies) if dependencies else None,
            responses=merged or None,
            **kwargs,
        )

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: `{key}（{N} 条路由）`。
        """
        return f"{self.key}（{len(self.routes)} 条路由）"


class RouterRegistry(BaseObject):
    """路由登记表：登记唯一性（`key` 拒重）+ 统一挂载。"""

    def __init__(self) -> None:
        """初始化空登记表（登记保序）。"""
        self._routers: dict[str, BaseRouter] = {}

    def register(self, router: BaseRouter) -> None:
        """登记路由（重复 `key` 拒重，不静默覆盖）。

        Args:
            router: 模块路由。

        Raises:
            ConflictError: `key` 已登记（10003）。
        """
        if router.key in self._routers:
            raise ConflictError(f"路由重复登记：{router.key}")
        self._routers[router.key] = router

    def get(self, key: str) -> BaseRouter | None:
        """按 `key` 取路由（未命中返回 None）。

        Args:
            key: 路由模块标识。

        Returns:
            BaseRouter | None: 路由；未命中为 None。
        """
        return self._routers.get(key)

    def keys(self) -> tuple[str, ...]:
        """已登记路由键（登记顺序）。

        Returns:
            tuple[str, ...]: 键元组。
        """
        return tuple(self._routers)

    def routers(self) -> tuple[BaseRouter, ...]:
        """已登记路由（登记顺序）。

        Returns:
            tuple[BaseRouter, ...]: 路由元组。
        """
        return tuple(self._routers.values())

    def mount(self, parent: APIRouter, *, prefix: str = "") -> None:
        """把全部已登记路由挂到父路由（统一挂载）。

        Args:
            parent: 父路由。
            prefix: 统一挂载前缀（默认空）。
        """
        for router in self._routers.values():
            parent.include_router(router, prefix=prefix)


_DEFAULT_REGISTRY = RouterRegistry()
"""进程级默认路由登记表（模块路由汇入的统一挂载入口）。"""


def router_registry() -> RouterRegistry:
    """取进程级默认路由登记表。

    Returns:
        RouterRegistry: 默认登记表实例。
    """
    return _DEFAULT_REGISTRY


def register_router(router: BaseRouter) -> None:
    """登记路由到默认登记表。

    Args:
        router: 模块路由。

    Raises:
        ConflictError: `key` 已登记（10003）。
    """
    _DEFAULT_REGISTRY.register(router)


def build_api_router(*, prefix: str = API_PREFIX) -> APIRouter:
    """构建内部接口聚合路由（把默认登记表的路由统一挂到 `prefix` 下）。

    Args:
        prefix: 统一挂载前缀（默认 `API_PREFIX`）。

    Returns:
        APIRouter: 聚合路由。
    """
    parent = APIRouter()
    _DEFAULT_REGISTRY.mount(parent, prefix=prefix)
    return parent


def mount_service_routers(routers: Sequence[BaseRouter], *, prefix: str = API_PREFIX) -> APIRouter:
    """构建**服务级**接口聚合路由（服务内独立登记表，避免多服务同名登记表跨服务串扰）。

    与 `register_router` / `build_api_router` 同口径（登记唯一性 + 统一前缀挂载），但使用服务内
    新建的 `RouterRegistry`。多服务同进程（如 monorepo 测试）下各服务登记互不影响；每服务进程
    仍是一份登记表。

    Args:
        routers: 本服务模块路由（继承 `BaseRouter`）。
        prefix: 统一挂载前缀（默认 `API_PREFIX`）。

    Returns:
        APIRouter: 本服务聚合路由。

    Raises:
        ConflictError: 模块路由 `key` 在本服务内重复（10003）。
    """
    registry = RouterRegistry()
    for router in routers:
        registry.register(router)
    parent = APIRouter()
    registry.mount(parent, prefix=prefix)
    return parent


def _build_query[QueryT](build: Callable[[], QueryT]) -> QueryT:
    """构造查询契约：契约级校验失败统一转参数错误（与请求级校验同一口径）。

    FastAPI 只把请求参数级校验失败转 `RequestValidationError`；依赖工厂内构造契约
    （如页码限深 / 游标 `limit`）抛出的 `ValidationError` 会漏到 500，故在此归一化。
    明细剔除 `ctx`（`value_error` 的 ctx 含异常对象、不可 JSON 序列化；具体约束信息已在 `msg`）。

    Args:
        build: 契约构造器。

    Returns:
        QueryT: 查询契约。

    Raises:
        ParamError: 契约校验失败（10001）。
    """
    try:
        return build()
    except ValidationError as exc:
        raise ParamError(data=exc.errors(include_context=False)) from exc


def page_query(
    page: Annotated[int, Query(ge=1, description="页码（从 1 起）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数（默认 20，上限 200）")] = 20,
    order_by: Annotated[str | None, Query(description="排序字段，逗号分隔多值（如 status,created_at）")] = None,
    order: Annotated[list[str] | None, Query(description="排序方向数组，与 order_by 位置一一对应")] = None,
) -> BasePageQuery:
    """页码分页参数绑定（含排序，复用 `BasePageQuery`）。

    Args:
        page: 页码。
        size: 每页条数。
        order_by: 排序字段。
        order: 排序方向数组。

    Returns:
        BasePageQuery: 分页请求契约。

    Raises:
        ParamError: 页码限深等契约校验失败（10001）。
    """
    return _build_query(lambda: BasePageQuery(page=page, size=size, order_by=order_by, order=order))


def sort_query(
    order_by: Annotated[str | None, Query(description="排序字段，逗号分隔多值")] = None,
    order: Annotated[list[str] | None, Query(description="排序方向数组，与 order_by 位置一一对应")] = None,
) -> BaseSortQuery:
    """排序参数绑定（复用 `BaseSortQuery`）。

    Args:
        order_by: 排序字段。
        order: 排序方向数组。

    Returns:
        BaseSortQuery: 排序请求契约。

    Raises:
        ParamError: 契约校验失败（10001）。
    """
    return _build_query(lambda: BaseSortQuery(order_by=order_by, order=order))


def cursor_query(
    cursor: Annotated[str | None, Query(description="游标（首页为空）")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="每批条数（默认 20，上限 200）")] = 20,
    order_by: Annotated[str | None, Query(description="排序字段，逗号分隔多值")] = None,
    order: Annotated[list[str] | None, Query(description="排序方向数组，与 order_by 位置一一对应")] = None,
) -> BaseCursorQuery:
    """游标分页参数绑定（含排序，复用 `BaseCursorQuery`）。

    Args:
        cursor: 游标。
        limit: 每批条数。
        order_by: 排序字段。
        order: 排序方向数组。

    Returns:
        BaseCursorQuery: 游标分页请求契约。

    Raises:
        ParamError: `limit` 上限等契约校验失败（10001）。
    """
    return _build_query(lambda: BaseCursorQuery(cursor=cursor, limit=limit, order_by=order_by, order=order))


def require_auth() -> None:
    """登录态依赖占位：恒定放行（**不解析 Bearer / 不校验 token**）。

    真实登录态解析（Bearer → 用户上下文）与未认证 401 随认证阶段回补；权限码校验沿用
    `bms_core.permission.base.require_permission`。路由可经 `dependencies=[Depends(require_auth)]`
    统一挂接，替换真实实现时调用面零改动。
    """
