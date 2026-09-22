"""通知中心占位路由：`/api/v1/notifications`（登录即可；真实取数 / 落库 / 推送随通知公告阶段）。

- 列表 / 详情（查看即已读）/ 未读计数 / 已读（批量 / 全部）/ 删除，统一经 `BaseNotificationCenter`。
- **未读数以服务端为唯一口径**：已读接口返回操作后的未读总数，前端据此校准角标。
- 静态路径（`/unread-count` `/read` `/read-all`）先于 `/{notification_id}` 登记，避免路径吞并。
"""

import json
from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_notification_center
from bms_core.core.exceptions import ParamError
from bms_core.notification.base import BaseNotificationCenter
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


def _parse_filters(raw: str | None) -> list[FilterSpec]:
    """解析筛选条件 JSON（`FilterSpec` 数组）。

    Args:
        raw: JSON 字符串；空 / None 表示无条件。

    Returns:
        list[FilterSpec]: 筛选条件列表。

    Raises:
        ParamError: 非合法 JSON 或非数组（10001）。
    """
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParamError("filters 不是合法 JSON") from exc
    if not isinstance(items, list):
        raise ParamError("filters 应为 JSON 数组")
    return [FilterSpec.model_validate(item) for item in cast("list[object]", items)]


def filter_query(
    keyword: Annotated[str | None, Query(description="关键字（跨字段模糊，命中列由后端定义）")] = None,
    filters: Annotated[str | None, Query(description="筛选条件 JSON（FilterSpec 数组）")] = None,
) -> BaseFilterQuery:
    """列表筛选参数绑定（复用 02-4-20 `BaseFilterQuery`）。

    Args:
        keyword: 关键字。
        filters: 筛选条件 JSON 字符串。

    Returns:
        BaseFilterQuery: 筛选契约（占位不执行筛选）。
    """
    return BaseFilterQuery(keyword=keyword, filters=_parse_filters(filters))


FilterDep = Annotated[BaseFilterQuery, Depends(filter_query)]


@router.get("")
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
    """当前未读总数（服务端唯一口径）。

    Args:
        center: 通知中心。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.unread_count()))


@router.post("/read")
async def mark_notifications_read(center: CenterDep, req: NotificationReadRequest) -> ApiResponse:
    """按 id 批量标记已读（返回操作后未读总数供前端校准角标）。

    Args:
        center: 通知中心。
        req: 批量已读请求。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`（操作后未读总数）。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.mark_read(req.ids)))


@router.post("/read-all")
async def mark_all_notifications_read(center: CenterDep) -> ApiResponse:
    """全部标记已读（返回操作后未读总数，恒 0）。

    Args:
        center: 通知中心。

    Returns:
        ApiResponse: 统一响应，data 为 `{count}`。
    """
    return ApiResponse.ok(UnreadCountResponse(count=await center.mark_all_read()))


@router.get("/{notification_id}")
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
        ApiResponse: 统一响应，data 为通知或 null。
    """
    return ApiResponse.ok(await center.detail(notification_id, mark_read=mark_read))


@router.delete("/{notification_id}")
async def delete_notification(center: CenterDep, notification_id: int) -> ApiResponse:
    """删除单条通知。

    Args:
        center: 通知中心。
        notification_id: 通知 ID。

    Returns:
        ApiResponse: 统一响应，data 为是否删除到既有通知。
    """
    return ApiResponse.ok(await center.delete(notification_id))
