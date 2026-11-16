"""归档执行记录端点：`/api/v1/archive/logs`（列表 / 详情 / 下载 / 销毁）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_object_storage, get_platform_read_db, get_platform_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.context import get_current_user_id
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.models.platform.archive import SysArchiveLog
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_core.storage.base import BaseObjectStorage
from bms_platform.domains.archive.schemas.archive import (
    ArchiveLogDestroyRequest,
    ArchiveLogItem,
    ArchiveLogPage,
    PresignedDownload,
)
from bms_platform.domains.archive.services.dispose import ArchiveDisposeService
from bms_platform.domains.archive.services.query import ArchiveQueryService

__all__ = ["router"]

router = BaseRouter(
    key="archive_logs",
    prefix="/archive/logs",
    tags=["archive"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("archive:query"))
_REQUIRE_DESTROY = Depends(require_permission("archive:destroy"))

ReadDbDep = Annotated[DbSession, Depends(get_platform_read_db)]
UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
StorageDep = Annotated[BaseObjectStorage, Depends(get_object_storage)]
PolicyIdQuery = Annotated[int | None, Query(description="策略主键筛选")]
TableQuery = Annotated[str | None, Query(description="表名筛选")]
TargetQuery = Annotated[str | None, Query(description="目标筛选（archive_db/minio/cleanup/destroy）")]
StatusQuery = Annotated[str | None, Query(description="状态筛选")]
StartedFromQuery = Annotated[datetime | None, Query(description="开始时间下限（UTC）")]
StartedToQuery = Annotated[datetime | None, Query(description="开始时间上限（UTC）")]


def _item(log: SysArchiveLog) -> ArchiveLogItem:
    """ORM → 响应契约。"""
    return ArchiveLogItem.model_validate(log)


def _page(rows: ConcurrentStableList[SysArchiveLog], total: int, page: int, size: int) -> ArchiveLogPage:
    """构造分页响应。"""
    return ArchiveLogPage(list=ConcurrentStableList(_item(row) for row in rows), total=total, page=page, size=size)


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_logs(
    session: ReadDbDep,
    storage: StorageDep,
    page: PageDep,
    policy_id: PolicyIdQuery = None,
    table_name: TableQuery = None,
    target: TargetQuery = None,
    status: StatusQuery = None,
    started_from: StartedFromQuery = None,
    started_to: StartedToQuery = None,
) -> ApiResponse[ArchiveLogPage]:
    """执行记录分页查询。

    Args:
        session: 平台库只读会话。
        storage: 对象存储（查询服务依赖注入用）。
        page: 分页参数。
        policy_id: 策略筛选。
        table_name: 表名筛选。
        target: 目标筛选。
        status: 状态筛选。
        started_from: 开始时间下限。
        started_to: 开始时间上限。

    Returns:
        ApiResponse[ArchiveLogPage]: 分页结果。
    """
    service = ArchiveQueryService(session, session, settings=get_settings(), storage=storage)
    rows, total = await service.list_logs(
        page=page.page,
        size=page.size,
        policy_id=policy_id,
        table_name=table_name,
        target=target,
        status=status,
        started_from=started_from,
        started_to=started_to,
    )
    return ApiResponse.ok(_page(rows, total, page.page, page.size))


@router.get("/{log_id}", dependencies=[_REQUIRE_QUERY])
async def get_log(log_id: int, session: ReadDbDep, storage: StorageDep) -> ApiResponse[ArchiveLogItem]:
    """执行记录详情。

    Args:
        log_id: 记录主键。
        session: 平台库只读会话。
        storage: 对象存储。

    Returns:
        ApiResponse[ArchiveLogItem]: 记录详情。
    """
    service = ArchiveQueryService(session, session, settings=get_settings(), storage=storage)
    return ApiResponse.ok(_item(await service.get_log(log_id)))


@router.get("/{log_id}/download", dependencies=[_REQUIRE_QUERY])
async def download(log_id: int, session: ReadDbDep, storage: StorageDep) -> ApiResponse[PresignedDownload]:
    """获取冷化文件预签名下载地址。

    Args:
        log_id: 记录主键。
        session: 平台库只读会话。
        storage: 对象存储。

    Returns:
        ApiResponse[PresignedDownload]: 预签名结果。
    """
    service = ArchiveQueryService(session, session, settings=get_settings(), storage=storage)
    return ApiResponse.ok(await service.download(log_id))


@router.post("/{log_id}/destroy", dependencies=[_REQUIRE_DESTROY])
async def destroy_log(
    log_id: int, request: ArchiveLogDestroyRequest, uow: UowDep, storage: StorageDep
) -> ApiResponse[ArchiveLogItem]:
    """销毁某批冷化文件（需二次确认）。

    Args:
        log_id: 记录主键。
        request: 销毁请求。
        uow: 平台库工作单元。
        storage: 对象存储。

    Returns:
        ApiResponse[ArchiveLogItem]: 销毁留痕记录。
    """
    service = ArchiveDisposeService(cast("DbSession", uow.session), cast("DbSession", uow.session), storage=storage)
    record = await service.destroy_log(log_id, confirm=request.confirm, operator_id=get_current_user_id())
    return ApiResponse.ok(_item(record))
