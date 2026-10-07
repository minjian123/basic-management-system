"""产品档案只读路由：清单（分页 + 筛选）与明细（只读，无写接口）。

- 数据源为平台库 `sys_product`（产品档案单一权威），经 `get_platform_read_db` 平台库只读会话取数
  （带租户上下文的请求仍读平台库）。
- 清单：`GET /api/v1/products`——分页 + `status` 筛选，响应 `ProductResponse` 分页结构。
- 明细：`GET /api/v1/products/{product_key}`——未登记统一 `NotFoundError`（10002 / 404 + 统一响应体）。
- 鉴权挂 `require_auth` 登录态占位（真实登录态与平台管理权限码随 RBAC 阶段回补）。
- 只读边界：仅 GET、不含密钥 / 敏感项（响应字段集固定为 `ProductResponse`）。
"""

from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import NotFoundError
from bms_core.db.session import DbSession
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_core.schemas.product import ProductResponse
from bms_platform.repositories.product_repository import ProductRepository

router = BaseRouter(
    key="products",
    prefix="/products",
    tags=["product"],
    dependencies=[Depends(require_auth)],
)

PlatformDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled / disabled / planned / retired）；缺省全部")]
ProductKeyPath = Annotated[str, Path(description="产品标识（product_key）")]


@router.get("")
async def list_products(
    session: PlatformDbDep,
    query: PageDep,
    status: StatusQuery = None,
) -> ApiResponse:
    """产品档案清单（只读，分页 + 筛选）。

    Args:
        session: 平台库只读会话。
        query: 分页与排序请求（page / size / order_by / order；排序白名单逐项校验、非法忽略）。
        status: 状态筛选；缺省返回全部。

    Returns:
        ApiResponse: 统一响应，data 为分页结构 `{list, total, page, size}`。
    """
    rows, total = await ProductRepository(session).page_products(query, status=status)
    page = BasePageResponse[ProductResponse](
        list=ConcurrentStableList(ProductResponse.model_validate(row) for row in rows),
        total=total,
        page=query.page,
        size=query.size,
    )
    return ApiResponse.ok(page)


@router.get("/{product_key}")
async def get_product(session: PlatformDbDep, product_key: ProductKeyPath) -> ApiResponse:
    """单条产品档案明细（只读；未登记 404）。

    Args:
        session: 平台库只读会话。
        product_key: 产品标识。

    Returns:
        ApiResponse: 统一响应，data 为产品档案记录（`ProductResponse`）。

    Raises:
        NotFoundError: 未登记（10002 / 404，全局处理器统一转响应）。
    """
    row = await ProductRepository(session).get_by_key(product_key)
    if row is None:
        raise NotFoundError(f"产品未登记：{product_key}")
    return ApiResponse.ok(ProductResponse.model_validate(row))
