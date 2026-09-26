"""api 层接口路由基座：统一模块路由基类、路由登记与统一挂载、参数绑定与鉴权依赖占位。

- `API_PREFIX`：内部接口统一前缀（`/api/v1`）；`main.py` 不再重复传前缀。
- `DEFAULT_RESPONSES`：统一错误响应文档（401 / 403 / 404 / 429 / 500 → `ApiResponse` 形态），
  作为路由默认 `responses` 进 OpenAPI 契约。
- `BaseRouter`：模块（能力域）路由基类（继承 FastAPI `APIRouter` + `BaseObject`）——统一前缀 /
  tags / 默认错误响应 / 元信息；模块路由一律继承它，不得裸建 `APIRouter`。
- `RouterRegistry` / `register_router` / `build_api_router`：路由登记（`key` 唯一拒重）与统一挂载。
- `page_query` / `sort_query` / `cursor_query`：分页 / 排序 / 游标参数统一 `Depends` 绑定工厂
  （复用 `BasePageQuery` / `BaseSortQuery` / `BaseCursorQuery`）。
- `require_auth`：登录态依赖（按 `[edge].require_gateway_identity` 门控可信边缘身份；开关关时恒定放行）；
  细粒度权限校验沿用 `require_permission`（阶段七）。
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, params
from pydantic import ValidationError

from bms_core.core.base import BaseObject
from bms_core.core.exceptions import AuthError, ConflictError, ParamError
from bms_core.edge.base import require_edge_identity
from bms_core.oauth.token import TOKEN_AUDIENCE_SERVICE
from bms_core.oauth.verify import BaseTokenVerifier, VerifiedToken, get_token_verifier
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
    "require_service",
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


def require_auth(request: Request) -> None:
    """登录态依赖：按 `[edge].require_gateway_identity` 门控可信边缘身份。

    开关关（dev / test）→ 恒定放行（保留占位语义，调用面 `Depends(require_auth)` 零改动）；
    开关开 → 取请求态可信身份（`require_edge_identity`），缺失（未认证 / 网关旁路）抛
    `AuthError`（20001 / 401）。细粒度权限码校验沿用 `bms_core.permission.base.require_permission`
    （阶段七）。

    Args:
        request: 请求对象（取应用配置与请求态可信身份）。

    Raises:
        AuthError: 旁路开关开启且无可信边缘身份（20001 / 401）。
    """
    settings = getattr(request.app.state, "settings", None)
    edge_settings = getattr(settings, "edge", None)
    if not bool(getattr(edge_settings, "require_gateway_identity", False)):
        return
    require_edge_identity(request)


def require_service(*allowed_services: str) -> Callable[..., Awaitable[VerifiedToken]]:
    """服务身份依赖工厂：仅接受有效服务 JWT（`aud=service`），可限定调用方服务标识。

    用于**内部端点**（服务间东西向直连、不经网关）：从 `Authorization: Bearer` 取令牌，经统一
    校验器按 `aud=service` 全校验（签名 / `exp` / `iss` / `aud`），再校验签发方服务标识在允许清单内。
    网关为用户请求换发的是 `sub=gateway` 的服务 JWT，若非白名单即拒——避免内部端点经网关被误信。

    Args:
        *allowed_services: 允许的调用方服务标识（`VerifiedToken.service`）；空 = 不限定。

    Returns:
        Callable[..., Awaitable[VerifiedToken]]: FastAPI 依赖（返回校验后的身份声明）。
    """

    async def dependency(
        verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> VerifiedToken:
        """校验入站服务 JWT（缺失 / 无效 / 非服务受众 / 非白名单一律拒）。

        Args:
            verifier: 统一令牌校验器。
            authorization: `Authorization` 头。

        Returns:
            VerifiedToken: 校验通过的服务身份声明。

        Raises:
            AuthError: 缺失 / 无效令牌或签发方不在允许清单（20001 / 401）。
        """
        token = _bearer_token(authorization)
        if token is None:
            raise AuthError("缺少服务身份凭证")
        verified = await verifier.verify(token, audience=TOKEN_AUDIENCE_SERVICE)
        if allowed_services and (verified.service or "") not in allowed_services:
            raise AuthError("服务身份不在允许清单")
        return verified

    return dependency


def _bearer_token(authorization: str | None) -> str | None:
    """取 Bearer 令牌（大小写不敏感）。

    Args:
        authorization: `Authorization` 头原始值。

    Returns:
        str | None: 令牌紧凑串；缺失 / 非 Bearer 为 None。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None
