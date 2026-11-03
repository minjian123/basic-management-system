"""审计日志查询端点：`/api/v1/operation-logs`、`/api/v1/login-logs`（06_01）。

- **鉴权**：`require_auth` + `log:query`（审计管理员）；只读，不提供新增 / 修改 / 删除。
- **库**：日志集中存平台服务库（`get_platform_read_db` 只读会话）。
- **分片**：查询服务按台账路由分片（前后各扩一月）；详情由雪花 ID 反解月份直接定位。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_read_db
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.session import DbSession
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.log.schemas.log import (
    LoginLogItem,
    LoginLogPage,
    OperationLogItem,
    OperationLogPage,
)
from bms_platform.domains.log.services.query import LoginLogQueryService, OperationLogQueryService

router = BaseRouter(
    key="audit_log",
    prefix="/operation-logs",
    tags=["log"],
    dependencies=[Depends(require_auth)],
)

_READ = Depends(require_permission("log:query"))
DbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
UserIdQuery = Annotated[int | None, Query(description="操作人主键")]
ModuleQuery = Annotated[str | None, Query(description="模块（精确）")]
ActionQuery = Annotated[str | None, Query(description="动作 / 权限码（精确）")]
StatusQuery = Annotated[int | None, Query(description="HTTP 状态码")]
OccurredFromQuery = Annotated[datetime | None, Query(description="事件时间下界（含）")]
OccurredToQuery = Annotated[datetime | None, Query(description="事件时间上界（含）")]
RecordIdPath = Annotated[int, Path(description="日志主键（雪花 ID）")]

login_router = BaseRouter(
    key="audit_login_log",
    prefix="/login-logs",
    tags=["log"],
    dependencies=[Depends(require_auth)],
)

UsernameQuery = Annotated[str | None, Query(description="登录名（模糊）")]
LoginStatusQuery = Annotated[str | None, Query(description="结果（success / failed）")]
IpQuery = Annotated[str | None, Query(description="客户端 IP（精确）")]


@router.get("", dependencies=[_READ])
async def list_operation_logs(
    session: DbDep,
    page: PageDep,
    user_id: UserIdQuery = None,
    module: ModuleQuery = None,
    action: ActionQuery = None,
    status: StatusQuery = None,
    occurred_from: OccurredFromQuery = None,
    occurred_to: OccurredToQuery = None,
) -> ApiResponse[OperationLogPage]:
    """操作日志分页查询（用户 / 模块 / 动作 / 状态 / 时间范围）。

    Args:
        session: 平台库只读会话。
        page: 分页参数。
        user_id: 操作人主键。
        module: 模块。
        action: 动作 / 权限码。
        status: HTTP 状态码。
        occurred_from: 事件时间下界。
        occurred_to: 事件时间上界。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    service = OperationLogQueryService(session, get_settings().audit_log)
    rows, total = await service.page(
        user_id=user_id,
        module=module,
        action=action,
        status=status,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page.page,
        size=page.size,
    )
    items = OperationLogPage(
        list=ConcurrentStableList(OperationLogItem.model_validate(dict(row)) for row in rows),
        total=total,
        page=page.page,
        size=page.size,
    )
    return ApiResponse.ok(items)


@router.get("/{record_id}", dependencies=[_READ])
async def get_operation_log(session: DbDep, record_id: RecordIdPath) -> ApiResponse[OperationLogItem]:
    """操作日志详情（含哈希值）。

    Args:
        session: 平台库只读会话。
        record_id: 日志主键。

    Returns:
        ApiResponse: 统一响应，data 为日志详情。
    """
    service = OperationLogQueryService(session, get_settings().audit_log)
    row = await service.detail(record_id)
    return ApiResponse.ok(OperationLogItem.model_validate(dict(row)))


@login_router.get("", dependencies=[_READ])
async def list_login_logs(
    session: DbDep,
    page: PageDep,
    username: UsernameQuery = None,
    status: LoginStatusQuery = None,
    ip: IpQuery = None,
    occurred_from: OccurredFromQuery = None,
    occurred_to: OccurredToQuery = None,
) -> ApiResponse[LoginLogPage]:
    """登录日志分页查询（用户名 / 状态 / IP / 时间范围）。

    Args:
        session: 平台库只读会话。
        page: 分页参数。
        username: 登录名（模糊）。
        status: 结果。
        ip: 客户端 IP。
        occurred_from: 事件时间下界。
        occurred_to: 事件时间上界。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    service = LoginLogQueryService(session, get_settings().audit_log)
    rows, total = await service.page(
        username=username,
        status=status,
        ip=ip,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page.page,
        size=page.size,
    )
    items = LoginLogPage(
        list=ConcurrentStableList(LoginLogItem.model_validate(dict(row)) for row in rows),
        total=total,
        page=page.page,
        size=page.size,
    )
    return ApiResponse.ok(items)


@login_router.get("/{record_id}", dependencies=[_READ])
async def get_login_log(session: DbDep, record_id: RecordIdPath) -> ApiResponse[LoginLogItem]:
    """登录日志详情（含失败原因与哈希值）。

    Args:
        session: 平台库只读会话。
        record_id: 日志主键。

    Returns:
        ApiResponse: 统一响应，data 为日志详情。
    """
    service = LoginLogQueryService(session, get_settings().audit_log)
    row = await service.detail(record_id)
    return ApiResponse.ok(LoginLogItem.model_validate(dict(row)))
