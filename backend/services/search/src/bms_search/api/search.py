"""全文检索占位路由：`/api/v1/search`（登录即可；真实 ES / 聚合 / 降级随全文检索阶段）。

- 多域聚合 `GET /search/global`、审计日志 `GET /search/logs`、文件内容 `GET /search/files`。
- 契约口径见 `app/globalsearch/base.py`：可检索域按权限并集、租户与数据范围检索侧强制、结果只返标识与高亮、
  降级字段与替代入口。
"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_audit_search, get_file_content_search, get_global_search
from bms_core.globalsearch.base import (
    DEFAULT_GLOBAL_SEARCH_SIZE,
    BaseAuditSearch,
    BaseFileContentSearch,
    BaseGlobalSearch,
)
from bms_core.schemas.common import ApiResponse

router = BaseRouter(
    key="search",
    prefix="/search",
    tags=["search"],
    dependencies=[Depends(require_auth)],
)

GlobalSearchDep = Annotated[BaseGlobalSearch, Depends(get_global_search)]
AuditSearchDep = Annotated[BaseAuditSearch, Depends(get_audit_search)]
FileContentSearchDep = Annotated[BaseFileContentSearch, Depends(get_file_content_search)]


@router.get("/global")
async def global_search(
    service: GlobalSearchDep,
    q: Annotated[str, Query(description="检索关键词")],
    types: Annotated[list[str] | None, Query(description="限定域（多值，缺省 = 全部可检索域）")] = None,
    page: Annotated[int, Query(ge=1, le=100, description="页码（从 1 起，限深 ≤ 100）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = DEFAULT_GLOBAL_SEARCH_SIZE,
) -> ApiResponse:
    """多域聚合检索（按域分组 + 高亮）。

    Args:
        service: 多域聚合检索契约。
        q: 检索关键词。
        types: 限定域。
        page: 页码。
        size: 每页条数。

    Returns:
        ApiResponse: 统一响应，data 为多域分组结果（含降级字段）。
    """
    return ApiResponse.ok(await service.search(q, types=types, page=page, size=size))


@router.get("/logs")
async def audit_search(
    service: AuditSearchDep,
    q: Annotated[str, Query(description="检索关键词")],
    start_time: Annotated[datetime, Query(description="起始时间（必填）")],
    end_time: Annotated[datetime, Query(description="结束时间（必填）")],
    log_type: Annotated[str | None, Query(description="日志类型过滤（operation / login / open / data_audit）")] = None,
    page: Annotated[int, Query(ge=1, le=100, description="页码（从 1 起，限深 ≤ 100）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = DEFAULT_GLOBAL_SEARCH_SIZE,
) -> ApiResponse:
    """审计日志检索（时间范围必填，单次 ≤ 31 天）。

    Args:
        service: 审计日志检索契约。
        q: 检索关键词。
        start_time: 起始时间。
        end_time: 结束时间。
        log_type: 日志类型过滤。
        page: 页码。
        size: 每页条数。

    Returns:
        ApiResponse: 统一响应，data 为审计日志命中（含降级字段）。
    """
    return ApiResponse.ok(
        await service.audit_logs(q, log_type=log_type, start_time=start_time, end_time=end_time, page=page, size=size)
    )


@router.get("/files")
async def file_content_search(
    service: FileContentSearchDep,
    q: Annotated[str, Query(description="检索关键词")],
    file_type: Annotated[str | None, Query(description="文件类型过滤")] = None,
    page: Annotated[int, Query(ge=1, le=100, description="页码（从 1 起，限深 ≤ 100）")] = 1,
    size: Annotated[int, Query(ge=1, le=200, description="每页条数")] = DEFAULT_GLOBAL_SEARCH_SIZE,
) -> ApiResponse:
    """文件内容检索（返回文件 ID 与上下文高亮）。

    Args:
        service: 文件内容检索契约。
        q: 检索关键词。
        file_type: 文件类型过滤。
        page: 页码。
        size: 每页条数。

    Returns:
        ApiResponse: 统一响应，data 为文件命中（含降级字段）。
    """
    return ApiResponse.ok(await service.file_content(q, file_type=file_type, page=page, size=size))
