"""查询方案占位路由：`/api/v1/query-schemes`（登录即可；真实落库 / 权限码随对应阶段）。

- 通用查询方案接口（泛化 `sys_query_scheme`）：一份表供字典高级查询（`target=items`）与列表筛选
  （`target=business`，`field_key=form_key`）共用。
- 个人方案免权限码；租户 / 共享方案维护需 `query:scheme`（真实随 RBAC 阶段）。
"""

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_query_scheme_store
from bms_core.core.exceptions import NotFoundError
from bms_core.listing.base import BaseQuerySchemeStore, QueryScheme, QuerySchemeTarget
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="query_scheme",
    prefix="/query-schemes",
    tags=["query_scheme"],
    dependencies=[Depends(require_auth)],
)

StoreDep = Annotated[BaseQuerySchemeStore, Depends(get_query_scheme_store)]
TargetQuery = Annotated[QuerySchemeTarget, Query(description="方案目标（items 字典条目 / business 列表筛选）")]
FieldKeyQuery = Annotated[str | None, Query(description="表单标识（business 时取 form_key）")]


@router.get("")
async def list_query_schemes(store: StoreDep, target: TargetQuery, field_key: FieldKeyQuery = None) -> ApiResponse:
    """列查询方案（按目标、可选按表单标识过滤）。

    Args:
        store: 查询方案存储。
        target: 方案目标。
        field_key: 表单标识。

    Returns:
        ApiResponse: 统一响应，data 为方案数组。
    """
    return ApiResponse.ok([scheme for scheme in await store.list(target, field_key=field_key)])


@router.get("/default")
async def resolve_default_scheme(store: StoreDep, target: TargetQuery, field_key: FieldKeyQuery = None) -> ApiResponse:
    """按三级优先级（个人 > 租户 > 平台）解析默认方案。

    Args:
        store: 查询方案存储。
        target: 方案目标。
        field_key: 表单标识。

    Returns:
        ApiResponse: 统一响应，data 为方案或 null。
    """
    return ApiResponse.ok(await store.resolve_default(target, field_key=field_key))


@router.get("/{scheme_id}")
async def get_query_scheme(store: StoreDep, scheme_id: int) -> ApiResponse:
    """查询方案详情。

    Args:
        store: 查询方案存储。
        scheme_id: 方案 ID。

    Returns:
        ApiResponse: 统一响应，data 为方案。

    Raises:
        NotFoundError: 方案不存在（10002 / 404，全局处理器统一转响应）。
    """
    scheme = await store.get(scheme_id)
    if scheme is None:
        raise NotFoundError(f"查询方案不存在：{scheme_id}")
    return ApiResponse.ok(scheme)


@router.post("")
async def save_query_scheme(store: StoreDep, scheme: QueryScheme) -> ApiResponse:
    """新建 / 保存方案。

    Args:
        store: 查询方案存储。
        scheme: 方案（`id` 为空表示新建）。

    Returns:
        ApiResponse: 统一响应，data 为保存后的方案。
    """
    return ApiResponse.ok(await store.save(scheme))


@router.put("/{scheme_id}")
async def update_query_scheme(store: StoreDep, scheme_id: int, scheme: QueryScheme) -> ApiResponse:
    """更新方案。

    Args:
        store: 查询方案存储。
        scheme_id: 方案 ID。
        scheme: 方案（以路径 ID 为准）。

    Returns:
        ApiResponse: 统一响应，data 为保存后的方案。
    """
    return ApiResponse.ok(await store.save(scheme.model_copy(update={"id": scheme_id})))


@router.delete("/{scheme_id}")
async def delete_query_scheme(store: StoreDep, scheme_id: int) -> ApiResponse:
    """删除方案。

    Args:
        store: 查询方案存储。
        scheme_id: 方案 ID。

    Returns:
        ApiResponse: 统一响应，data 为 null。
    """
    await store.delete(scheme_id)
    return ApiResponse.ok()
