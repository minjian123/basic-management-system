"""通知中心路由：`/api/v1/notifications`（列表 / 详情 / 未读数 / 已读 / 删除）。

- 列表 / 详情 / 已读 / 删除挂权限码；未读数（角标）属登录态内建能力，不设权限码。
- **未读数以服务端为唯一口径**：已读接口返回操作后的未读总数，前端据此校准角标。
- 静态路径（`/unread-count` `/read` `/read-all`）先于 `/{notification_id}` 登记，避免路径吞并。
"""

import json
from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_notification_center
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.notification.base import BaseNotificationCenter
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.filters import BaseFilterQuery, FilterSpec
from bms_core.schemas.notification import NotificationReadRequest, UnreadCountResponse
from bms_core.schemas.pagination import BasePageQuery

router = BaseRouter(
    key="notification",
    prefix="/notifications",
    tags=["notification"],
    dependencies=[Depends(require_auth)],
)

CenterDep = Annotated[BaseNotificationCenter, Depends(get_notification_center)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]

_REQUIRE_QUERY = Depends(require_permission("notification:query"))
_REQUIRE_UPDATE = Depends(require_permission("notification:update"))
_REQUIRE_DELETE = Depends(require_permission("notification:delete"))


def _parse_filters(raw: str | None) -> ConcurrentStableList[FilterSpec]:
    """解析筛选条件 JSON（`FilterSpec` 数组）。

    Args:
        raw: JSON 字符串；空 / None 表示无条件。

    Returns:
        ConcurrentStableList[FilterSpec]: 筛选条件列表。

    Raises:
        ParamError: 非合法 JSON 或非数组（10001）。
    """
    if not raw:
        return ConcurrentStableList()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParamError("filters 不是合法 JSON") from exc
    if not isinstance(items, list):
        raise ParamError("filters 应为 JSON 数组")
    return ConcurrentStableList(FilterSpec.model_validate(item) for item in cast("list[object]", items))


def filter_query(
    keyword: Annotated[str | None, Query(description="关键字（匹配标题）")] = None,
    filters: Annotated[str | None, Query(description="筛选条件 JSON（FilterSpec 数组）")] = None,
    notification_type: Annotated[
        str | None, Query(alias="type", description="通知类型（system/approval/alert/import）")
    ] = None,
    is_read: Annotated[bool | None, Query(description="已读状态（true / false）")] = None,
) -> BaseFilterQuery:
    """列表筛选参数绑定（显式 type / is_read 转为通用 FilterSpec）。

    Args:
        keyword: 关键字（匹配标题）。
        filters: 筛选条件 JSON 字符串。
        notification_type: 通知类型。
        is_read: 已读状态。

    Returns:
        BaseFilterQuery: 筛选契约。
    """
    conditions = _parse_filters(filters)
    if notification_type:
        conditions.add(FilterSpec(field="type", operator="eq", value=notification_type))
    if is_read is not None:
        conditions.add(FilterSpec(field="is_read", operator="eq", value=is_read))
    return BaseFilterQuery(keyword=keyword, filters=conditions)


FilterDep = Annotated[BaseFilterQuery, Depends(filter_query)]


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_notifications(center: CenterDep, filter: FilterDep, page: PageDep) -> ApiResponse:
    """列当前用户通知（筛选 + 分页）。

    Args:
        center: 通知中心。
        filter: 筛选契约。
        page: 分页契约。

    Returns:
        ApiResponse: 统一响应，data 为分页通知。
    """
    return ApiResponse.ok(await center.list(filter, page))


@router.get("/unread-count")
async def get_unread_count(center: CenterDep) -> ApiResponse:
    """当前未读总数（服务端唯一口径；登录即可）。

    Args:
        center: 通知中心。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.unread_count()))


@router.post("/read", dependencies=[_REQUIRE_UPDATE])
async def mark_notifications_read(center: CenterDep, req: NotificationReadRequest) -> ApiResponse:
    """按 id 批量标记已读（返回操作后未读总数供前端校准角标）。

    Args:
        center: 通知中心。
        req: 批量已读请求。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`（操作后未读总数）。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.mark_read(req.ids)))


@router.post("/read-all", dependencies=[_REQUIRE_UPDATE])
async def mark_all_notifications_read(center: CenterDep) -> ApiResponse:
    """全部标记已读（返回操作后未读总数，恒 0）。

    Args:
        center: 通知中心。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.mark_all_read()))


@router.get("/{notification_id}", dependencies=[_REQUIRE_QUERY])
async def get_notification_detail(
    center: CenterDep,
    notification_id: int,
    mark_read: Annotated[bool, Query(description="命中是否标记已读（默认 true，查看即已读）")] = True,
) -> ApiResponse:
    """取通知详情（查看即已读）。

    Args:
        center: 通知中心。
        notification_id: 通知 ID。
        mark_read: 命中是否标记已读。

    Returns:
        ApiResponse: 统一响应，data 为通知。
    """
    return ApiResponse.ok(await center.detail(notification_id, mark_read=mark_read))


@router.delete("/{notification_id}", dependencies=[_REQUIRE_DELETE])
async def delete_notification(center: CenterDep, notification_id: int) -> ApiResponse:
    """删除单条通知（软删除，仅本人）。

    Args:
        center: 通知中心。
        notification_id: 通知 ID。

    Returns:
        ApiResponse: 统一响应，data 为是否删除到既有通知。
    """
    return ApiResponse.ok(await center.delete(notification_id))
