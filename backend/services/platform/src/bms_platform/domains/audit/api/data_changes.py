"""数据变更审计查询端点：`/api/v1/audit/data-changes`（06_02）。

- **鉴权**：`require_auth` + `log:query`（审计管理员）；只读，不提供新增 / 修改 / 删除。
- **库**：数据变更审计集中存平台服务库（`get_platform_read_db` 只读会话）。
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
from bms_platform.domains.audit.schemas.data_change import DataChangeItem, DataChangePage
from bms_platform.domains.audit.services.data_change import DataChangeQueryService

router = BaseRouter(
    key="audit_data_change",
    prefix="/audit/data-changes",
    tags=["audit"],
    dependencies=[Depends(require_auth)],
)

_READ = Depends(require_permission("log:query"))
DbDep = Annotated[DbSession, Depends(get_platform_read_db)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
TableQuery = Annotated[str | None, Query(description="被审计表名（精确）")]
RecordIdQuery = Annotated[int | None, Query(description="被审计记录主键")]
OperatorQuery = Annotated[int | None, Query(description="操作人主键")]
DomainQuery = Annotated[str | None, Query(description="业务域（精确）")]
FieldQuery = Annotated[str | None, Query(description="变更字段名（精确）")]
OccurredFromQuery = Annotated[datetime | None, Query(description="事件时间下界（含）")]
OccurredToQuery = Annotated[datetime | None, Query(description="事件时间上界（含）")]
RecordIdPath = Annotated[int, Path(description="审计主键（雪花 ID）")]


@router.get("", dependencies=[_READ])
async def list_data_changes(
    session: DbDep,
    page: PageDep,
    table_name: TableQuery = None,
    record_id: RecordIdQuery = None,
    operator_id: OperatorQuery = None,
    domain_key: DomainQuery = None,
    field: FieldQuery = None,
    occurred_from: OccurredFromQuery = None,
    occurred_to: OccurredToQuery = None,
) -> ApiResponse[DataChangePage]:
    """数据变更审计分页查询（表名 / 记录 / 操作人 / 域 / 字段 / 时间范围）。

    Args:
        session: 平台库只读会话。
        page: 分页参数。
        table_name: 被审计表名。
        record_id: 被审计记录主键。
        operator_id: 操作人主键。
        domain_key: 业务域。
        field: 变更字段名。
        occurred_from: 事件时间下界。
        occurred_to: 事件时间上界。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    service = DataChangeQueryService(session, get_settings().audit_log)
    rows, total = await service.page(
        table_name=table_name,
        record_id=record_id,
        operator_id=operator_id,
        domain_key=domain_key,
        field=field,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        page=page.page,
        size=page.size,
    )
    items = DataChangePage(
        list=ConcurrentStableList(DataChangeItem.model_validate(dict(row)) for row in rows),
        total=total,
        page=page.page,
        size=page.size,
    )
    return ApiResponse.ok(items)


@router.get("/{record_id}", dependencies=[_READ])
async def get_data_change(session: DbDep, record_id: RecordIdPath) -> ApiResponse[DataChangeItem]:
    """数据变更审计详情（含链字段 `prev_hash` / `record_hash`）。

    Args:
        session: 平台库只读会话。
        record_id: 审计主键。

    Returns:
        ApiResponse: 统一响应，data 为审计详情。

    Raises:
        DataAuditLogNotFoundError: 记录不存在（90401 / 404）。
    """
    service = DataChangeQueryService(session, get_settings().audit_log)
    row = await service.detail(record_id)
    return ApiResponse.ok(DataChangeItem.model_validate(dict(row)))
