"""归档数据端点：`/api/v1/archive/data`（只读查询 / 单条销毁）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_archive_read_db, get_archive_write_db, get_object_storage, get_platform_uow
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import get_current_user_id
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.archive import SysArchiveRecord
from bms_core.permission.base import BasePermissionChecker, get_permission_checker, require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.schemas.archive import (
    ArchiveDataDestroyRequest,
    ArchiveDataItem,
    ArchiveDataPage,
    ArchiveDataQuery,
    ArchiveLogItem,
)
from bms_platform.domains.archive.services.dispose import ArchiveDisposeService
from bms_platform.domains.archive.services.query import ArchiveQueryService

__all__ = ["router"]

router = BaseRouter(
    key="archive_data",
    prefix="/archive/data",
    tags=["archive"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("archive:query"))
_REQUIRE_DESTROY = Depends(require_permission("archive:destroy"))

ArchiveReadDep = Annotated[DbSession, Depends(get_archive_read_db)]
ArchiveWriteDep = Annotated[DbSession, Depends(get_archive_write_db)]
UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StorageDep = Annotated[BaseObjectStorage, Depends(get_object_storage)]
CheckerDep = Annotated[BasePermissionChecker, Depends(get_permission_checker)]


def _item(record: SysArchiveRecord, payload: ConcurrentStableDict[str, object]) -> ArchiveDataItem:
    """构造归档数据行响应。"""
    return ArchiveDataItem(
        id=record.id,
        tenant_id=record.tenant_id,
        source_table=record.source_table,
        source_id=record.source_id,
        source_month=record.source_month,
        policy_id=record.policy_id,
        batch_id=record.batch_id,
        archived_at=record.archived_at,
        payload=payload,
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def query_data(
    session: ArchiveReadDep,
    storage: StorageDep,
    checker: CheckerDep,
    page: PageDep,
    source_table: str | None = None,
    source_id: str | None = None,
    source_month: str | None = None,
    tenant_id: int | None = None,
    stored_from: datetime | None = None,
    stored_to: datetime | None = None,
) -> ApiResponse[ArchiveDataPage]:
    """归档数据只读查询（只查归档库）。

    Args:
        session: 归档库只读会话。
        storage: 对象存储（查询服务依赖注入用）。
        checker: 权限检查器（判定审计管理员是否可跨租户）。
        page: 分页参数。
        source_table: 源逻辑表名。
        source_id: 源行主键。
        source_month: 源分片月份。
        tenant_id: 租户主键（审计管理员可跨租户）。
        stored_from: 归档起始时刻。
        stored_to: 归档结束时刻。

    Returns:
        ApiResponse[ArchiveDataPage]: 分页结果。
    """
    query = ArchiveDataQuery(
        source_table=source_table,
        source_id=source_id,
        source_month=source_month,
        tenant_id=tenant_id,
        stored_from=stored_from,
        stored_to=stored_to,
    )
    service = ArchiveQueryService(session, session, settings=get_settings(), storage=storage)
    rows, total = await service.query_data(
        query, page=page.page, size=page.size, allow_cross_tenant=checker.check("log:query")
    )
    items = ConcurrentStableList(_item(row, service.decode(row)) for row in rows)
    return ApiResponse.ok(ArchiveDataPage(list=items, total=total, page=page.page, size=page.size))


@router.post("/destroy", dependencies=[_REQUIRE_DESTROY])
async def destroy_data(
    request: ArchiveDataDestroyRequest,
    uow: UowDep,
    archive_session: ArchiveWriteDep,
    storage: StorageDep,
) -> ApiResponse[ArchiveLogItem]:
    """销毁单条归档行（需二次确认）。

    Args:
        request: 销毁请求。
        uow: 平台库工作单元。
        archive_session: 归档库写会话。
        storage: 对象存储。

    Returns:
        ApiResponse[ArchiveLogItem]: 销毁留痕记录。
    """
    service = ArchiveDisposeService(cast("DbSession", uow.session), archive_session, storage=storage)
    record = await service.destroy_record(
        source_table=request.source_table,
        source_id=request.source_id,
        confirm=request.confirm,
        operator_id=get_current_user_id(),
    )
    return ApiResponse.ok(ArchiveLogItem.model_validate(record))
