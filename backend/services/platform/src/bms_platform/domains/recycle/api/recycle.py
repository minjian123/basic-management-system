"""回收站端点：`/api/v1/recycle`（模块 / 列表 / 详情 / 恢复 / 清理记录）。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Header, Path, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import (
    current_tenant_id_of,
    get_audit_capturer,
    get_cache_region,
    get_idempotency_store,
    get_tenant,
    get_uow,
)
from bms_core.audit.base import AuditCapturer
from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.session import DbSession
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.recycle.schemas.recycle import (
    RecycleCleanupItem,
    RecycleCleanupPage,
    RecycleDetailResponse,
    RecycleItem,
    RecycleItemPage,
    RecycleModuleItem,
    RecycleModulesResponse,
    RecycleRestoreRequest,
    RecycleRestoreResult,
    RecycleTableItem,
)
from bms_platform.domains.recycle.services.query import RecycleQueryService
from bms_platform.domains.recycle.services.restore import RecycleRestoreService

__all__ = ["router"]

router = BaseRouter(
    key="recycle",
    prefix="/recycle",
    tags=["recycle"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("recycle:query"))
_REQUIRE_RESTORE = Depends(require_permission("recycle:restore"))

UowDep = Annotated[UnitOfWork, Depends(get_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
CacheDep = Annotated[CacheRegion, Depends(get_cache_region)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
IdempotencyKeyHeader = Annotated[str | None, Header(alias=IDEMPOTENCY_HEADER, description="幂等键（恢复去重）")]
TableQuery = Annotated[str, Query(min_length=1, max_length=64, description="逻辑表名（须在回收站纳管范围）")]
KeywordQuery = Annotated[str | None, Query(max_length=128, description="关键字（按表规格关键字列匹配）")]
DeletedFromQuery = Annotated[datetime | None, Query(description="删除时间下界（UTC；含）")]
DeletedToQuery = Annotated[datetime | None, Query(description="删除时间上界（UTC；含）")]
CleanupTableQuery = Annotated[str | None, Query(max_length=64, description="清理表名筛选")]
CleanupStatusQuery = Annotated[str | None, Query(description="清理状态筛选（running / success / failed）")]
StartedFromQuery = Annotated[datetime | None, Query(description="清理开始时间下界（UTC；含）")]
StartedToQuery = Annotated[datetime | None, Query(description="清理开始时间上界（UTC；含）")]
TablePath = Annotated[str, Path(min_length=1, max_length=64, description="逻辑表名（须在回收站纳管范围）")]


def _query_service(uow: UnitOfWork) -> RecycleQueryService:
    """构造查询服务。"""
    return RecycleQueryService(cast("DbSession", uow.session), get_settings().recycle_options)


def _restore_service(uow: UnitOfWork, audit: AuditCapturer, cache: CacheRegion) -> RecycleRestoreService:
    """构造恢复服务。"""
    return RecycleRestoreService(
        cast("DbSession", uow.session),
        get_settings().recycle_options,
        audit=audit,
        cache=cache,
    )


@router.get("/modules", dependencies=[_REQUIRE_QUERY])
async def list_modules(uow: UowDep) -> ApiResponse[RecycleModulesResponse]:
    """取可回收模块 / 表清单与删除计数。

    Args:
        uow: 租户库工作单元。

    Returns:
        ApiResponse[RecycleModulesResponse]: 模块分组。
    """
    modules = await _query_service(uow).modules()
    items: ConcurrentStableList[RecycleModuleItem] = ConcurrentStableList()
    for module in modules:
        items.add(
            RecycleModuleItem(
                module_key=module.module_key,
                module_label=module.module_label,
                deleted_count=module.deleted_count,
                tables=ConcurrentStableList(
                    RecycleTableItem(table=table.table, label=table.label, deleted_count=table.deleted_count)
                    for table in module.tables
                ),
            )
        )
    return ApiResponse.ok(RecycleModulesResponse(items=items))


@router.get("/items", dependencies=[_REQUIRE_QUERY])
async def list_items(
    uow: UowDep,
    page: PageDep,
    table: TableQuery,
    keyword: KeywordQuery = None,
    deleted_from: DeletedFromQuery = None,
    deleted_to: DeletedToQuery = None,
) -> ApiResponse[RecycleItemPage]:
    """单表分页查询软删除数据。

    Args:
        uow: 租户库工作单元。
        page: 分页参数。
        table: 逻辑表名。
        keyword: 关键字。
        deleted_from: 删除时间下界。
        deleted_to: 删除时间上界。

    Returns:
        ApiResponse[RecycleItemPage]: 分页结果。
    """
    rows, total = await _query_service(uow).page(
        table,
        keyword=keyword,
        deleted_from=deleted_from,
        deleted_to=deleted_to,
        page=page.page,
        size=page.size,
    )
    items: ConcurrentStableList[RecycleItem] = ConcurrentStableList(
        RecycleItem(table=row.table, id=row.id, title=row.title, deleted_at=row.deleted_at, deleted_by=row.deleted_by)
        for row in rows
    )
    return ApiResponse.ok(RecycleItemPage(list=items, total=total, page=page.page, size=page.size))


@router.get("/items/{table}/{row_id}", dependencies=[_REQUIRE_QUERY])
async def get_item(uow: UowDep, table: TablePath, row_id: int) -> ApiResponse[RecycleDetailResponse]:
    """取软删除数据详情（展示列快照）。

    Args:
        uow: 租户库工作单元。
        table: 逻辑表名。
        row_id: 记录主键。

    Returns:
        ApiResponse[RecycleDetailResponse]: 详情。
    """
    detail = await _query_service(uow).detail(table, row_id)
    return ApiResponse.ok(
        RecycleDetailResponse(
            table=detail.table,
            id=detail.id,
            title=detail.title,
            deleted_at=detail.deleted_at,
            deleted_by=detail.deleted_by,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            fields=ConcurrentStableDict(detail.fields),
        )
    )


@router.post("/restore", dependencies=[_REQUIRE_RESTORE])
async def restore_item(
    request: RecycleRestoreRequest,
    uow: UowDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    audit: AuditDep,
    cache: CacheDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse[RecycleRestoreResult]:
    """恢复一条软删除数据（支持幂等键）。

    Args:
        request: 恢复请求（表名 + 主键）。
        uow: 租户库工作单元。
        idempotency: 幂等基座。
        tenant: 解析链租户上下文（幂等键作用域位）。
        audit: 字段级审计捕获器。
        cache: 缓存 Region（恢复后版本失效）。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse[RecycleRestoreResult]: 恢复结果。
    """
    key: str | None = None
    if idempotency_key:
        key = build_idempotency_key(key=idempotency_key, tenant=current_tenant_id_of(tenant))
        if not await idempotency.begin(key):
            payload = await idempotency.load(key)
            if payload is not None:
                return ApiResponse.ok(RecycleRestoreResult.model_validate(payload))
    service = _restore_service(uow, audit, cache)
    async with uow.begin():
        outcome = await service.restore(request.table, int(request.id))
    result = RecycleRestoreResult(
        table=outcome.table,
        id=outcome.id,
        title=outcome.title,
        restored=True,
        cascaded=ConcurrentStableDict(outcome.cascaded),
    )
    if key is not None:
        await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(result)


@router.get("/cleanups", dependencies=[_REQUIRE_QUERY])
async def list_cleanups(
    uow: UowDep,
    page: PageDep,
    table_name: CleanupTableQuery = None,
    status: CleanupStatusQuery = None,
    started_from: StartedFromQuery = None,
    started_to: StartedToQuery = None,
) -> ApiResponse[RecycleCleanupPage]:
    """清理批次记录分页。

    Args:
        uow: 租户库工作单元。
        page: 分页参数。
        table_name: 表名筛选。
        status: 状态筛选。
        started_from: 开始时间下界。
        started_to: 开始时间上界。

    Returns:
        ApiResponse[RecycleCleanupPage]: 分页结果。
    """
    rows, total = await _query_service(uow).cleanups(
        table_name=table_name,
        status=status,
        started_from=started_from,
        started_to=started_to,
        page=page.page,
        size=page.size,
    )
    items: ConcurrentStableList[RecycleCleanupItem] = ConcurrentStableList(
        RecycleCleanupItem.model_validate(row) for row in rows
    )
    return ApiResponse.ok(RecycleCleanupPage(list=items, total=total, page=page.page, size=page.size))
