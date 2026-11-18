"""卡片管理端点：`/api/v1/dashboard/cards`（11_01）。

- **鉴权**：模块级 `require_auth`；读端点 `dashboard:query`、写端点 `dashboard:manage`；
- **双轨制**：内置卡由平台种子登记、租户**只可停用**（改定义 / 删除一律 `40308`）；数据集卡租户自建；
- **按码定位**：路径用卡片业务键 `code`（稳定不变），不用雪花 ID。
"""

from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_auth
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_platform.api.locale import accept_locale, locale_scope
from bms_platform.domains.dashboard.api.deps import ServiceDep
from bms_platform.domains.dashboard.schemas.card import (
    DashboardCardCreate,
    DashboardCardDeleteResult,
    DashboardCardList,
    DashboardCardRow,
    DashboardCardUpdate,
)

__all__ = ["router"]

router = BaseRouter(
    key="dashboard_cards",
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

_REQUIRE_QUERY = Depends(require_permission("dashboard:query"))
_REQUIRE_MANAGE = Depends(require_permission("dashboard:manage"))

CardTypeQuery = Annotated[str | None, Query(max_length=16, description="卡片类型（builtin / dataset）")]


@router.get("/cards", dependencies=[_REQUIRE_QUERY])
async def list_cards(
    request: Request, service: ServiceDep, card_type: CardTypeQuery = None
) -> ApiResponse[DashboardCardList]:
    """卡片列表（含停用；按 `sort` 升序）。

    需要 `dashboard:query`。

    Args:
        request: 请求对象（取请求语言）。
        service: 工作台服务。
        card_type: 卡片类型筛选（可选）。

    Returns:
        ApiResponse[DashboardCardList]: 统一响应，data 为卡片清单。
    """
    return ApiResponse.ok(await service.list_cards(card_type=card_type, locale=accept_locale(request)))


@router.post("/cards", dependencies=[_REQUIRE_MANAGE])
async def create_card(
    request: Request, service: ServiceDep, payload: DashboardCardCreate
) -> ApiResponse[DashboardCardRow]:
    """新建数据集卡。

    需要 `dashboard:manage`；内置卡 `40308`、码重复 `40302`、数据集不可用 `40303`。

    Args:
        request: 请求对象（取请求语言）。
        service: 工作台服务。
        payload: 新建请求。

    Returns:
        ApiResponse[DashboardCardRow]: 统一响应，data 为新建的卡片行。
    """
    return ApiResponse.ok(await service.create_card(payload=payload, locale=accept_locale(request)))


@router.put("/cards/{code}", dependencies=[_REQUIRE_MANAGE])
async def update_card(
    request: Request, service: ServiceDep, code: str, payload: DashboardCardUpdate
) -> ApiResponse[DashboardCardRow]:
    """编辑卡片（数据集卡全字段；内置卡只允许改状态）。

    需要 `dashboard:manage`；内置卡改定义 `40308`、卡片不存在 `40301`。

    Args:
        request: 请求对象（取请求语言）。
        service: 工作台服务。
        code: 卡片标识。
        payload: 编辑请求。

    Returns:
        ApiResponse[DashboardCardRow]: 统一响应，data 为更新后的卡片行。
    """
    return ApiResponse.ok(await service.update_card(code=code, payload=payload, locale=accept_locale(request)))


@router.delete("/cards/{code}", dependencies=[_REQUIRE_MANAGE])
async def delete_card(service: ServiceDep, code: str) -> ApiResponse[DashboardCardDeleteResult]:
    """删除卡片（数据集卡软删除；内置卡拒绝）。

    需要 `dashboard:manage`；内置卡 `40308`、卡片不存在 `40301`。

    Args:
        service: 工作台服务。
        code: 卡片标识。

    Returns:
        ApiResponse[DashboardCardDeleteResult]: 统一响应，data 为删除结果。
    """
    applied = await service.delete_card(code=code)
    return ApiResponse.ok(DashboardCardDeleteResult(applied=applied))
