"""服务目录只读路由：清单（分页 + 筛选）与明细（只读，无写接口）。

- 数据源为平台库 `sys_module`（服务目录单一权威），经 `get_platform_read_db` 平台库只读会话取数
  （带租户上下文的请求仍读平台库）。
- 清单：`GET /api/v1/modules`——分页 + `status` / `group` 筛选，响应 `ModuleResponse` 分页结构。
- 快照：`GET /api/v1/modules/snapshot`——**全量清单（不分页）**，供各服务**启动接库校验**对账
  （06_01 起非目录权威服务经 `service_client` 调本接口，见 `bms_core/catalog/loader.py`）。
- 明细：`GET /api/v1/modules/{service_key}`——`service_key` 优先、未命中回退 `module_key`；
  未登记统一 `NotFoundError`（10002 / 404 + 统一响应体）。
- 鉴权挂 `require_auth` 登录态占位（真实登录态与平台管理权限码随认证 / RBAC 阶段回补）。
- 只读边界：仅 GET、不含密钥 / 敏感项（响应字段集固定为 `ModuleResponse`）。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db
from bms_core.core.exceptions import NotFoundError
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.module import ModuleResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_platform.repositories.module_repository import ModuleRepository

router = BaseRouter(
    key="modules",
    prefix="/modules",
    tags=["module"],
    dependencies=[Depends(require_auth)],
)

PlatformDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled / disabled / planned）；缺省全部")]
GroupQuery = Annotated[str | None, Query(description="归属分组筛选（foundation / capability / product）；缺省全部")]
ServiceKeyPath = Annotated[str, Path(description="服务标识（service_key；未命中回退 module_key）")]


@router.get("")
async def list_modules(
    session: PlatformDbDep,
    query: PageDep,
    status: StatusQuery = None,
    group: GroupQuery = None,
) -> ApiResponse:
    """服务目录清单（只读，分页 + 筛选）。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（page / size / order_by / order；排序白名单逐项校验、非法忽略）。
        status: 状态筛选；缺省返回全部。
        group: 归属分组筛选；缺省返回全部。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await ModuleRepository(session).page_catalog(query, group=group, status=status)
    page = BasePageResponse[ModuleResponse](
        list=[ModuleResponse.model_validate(row) for row in rows],
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/snapshot")
async def catalog_snapshot(session: PlatformDbDep) -> ApiResponse:
    """服务目录快照（只读，全量清单不分页）。

    供各服务启动接库校验对账（`validate_catalog`）：字段与 `sys_module` 登记一致，
    响应 `data` 为清单数组（**注意**：路径须先于 `/modules/{service_key}` 注册，避免被明细路由吞掉）。

    Args:
        session: 平台库只读会话。

    Returns:
        ApiResponse: 统一响应，data 为服务目录记录数组（`ModuleResponse`）。
    """
    rows = await ModuleRepository(session).list_catalog()
    return ApiResponse.ok([ModuleResponse.model_validate(row) for row in rows])


@router.get("/{service_key}")
async def get_module(session: PlatformDbDep, service_key: ServiceKeyPath) -> ApiResponse:
    """单条服务目录明细（只读；未登记 404）。

    Args:
        session: 平台库只读会话。
        service_key: 服务标识（service_key 优先，未命中回退 module_key）。

    Returns:
        ApiResponse: 统一响应，data 为服务目录记录（`ModuleResponse`）。

    Raises:
        NotFoundError: 未登记（10002 / 404，全局处理器统一转响应）。
    """
    repository = ModuleRepository(session)
    row = await repository.get_by_service_key(service_key)
    if row is None:
        row = await repository.get_by_key(service_key)
    if row is None:
        raise NotFoundError(f"服务未登记：{service_key}")
    return ApiResponse.ok(ModuleResponse.model_validate(row))
