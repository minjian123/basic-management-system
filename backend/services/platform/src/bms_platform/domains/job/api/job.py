"""作业中心平台用户面：`/api/v1/jobs`（类型目录 / 统一列表 / 详情 / 取消 / 重试）。

- **读投影**：列表与详情读 `sys_job_monitor`（平台库），不跨服务查库；
- **命令转发**：取消 / 重试按投影里的 `service_key` 调目标服务内部端点（`JobInternalClient`），
  业务错误码（`71xxx`）原样映射回用户面；
- **权限**：查询挂 `job:query`，取消 / 重试挂 `job:manage`。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_uow
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.exceptions import JobNotFoundError
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs.client import JobInternalClient, build_service_client
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.job import JobActionResponse, JobCancelRequest
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.job.repositories.job import JobMonitorRepository, JobTypeRepository
from bms_platform.domains.job.schemas.job import (
    JobMonitorItem,
    JobMonitorPage,
    JobTypeItem,
    JobTypePage,
)
from bms_platform.domains.job.services.catalog import JobCatalogService

router = BaseRouter(
    key="job",
    prefix="/jobs",
    tags=["job"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("job:query"))
_REQUIRE_MANAGE = Depends(require_permission("job:manage"))

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
ServiceQuery = Annotated[str | None, Query(description="提供方服务键筛选")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（queued/running/succeeded/failed/canceled/dead）")]
TypeQuery = Annotated[str | None, Query(description="作业类型筛选")]


def _client() -> JobInternalClient:
    """构造内部契约客户端。

    Returns:
        JobInternalClient: 客户端。
    """
    return JobInternalClient(build_service_client())


@router.get("/types", dependencies=[_REQUIRE_QUERY])
async def list_job_types(
    uow: UowDep, page: PageDep, service_key: ServiceQuery = None, status: StatusQuery = None
) -> ApiResponse:
    """作业类型目录（读 `sys_job_type` 声明投影）。

    Args:
        uow: 平台库工作单元。
        page: 分页参数。
        service_key: 提供方服务筛选。
        status: 目录状态筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    rows, total = await JobCatalogService(JobTypeRepository(cast("DbSession", uow.session))).page(
        page=page.page, size=page.size, service_key=service_key, status=status
    )
    items = ConcurrentStableList(JobTypeItem.model_validate(row) for row in rows)
    return ApiResponse.ok(JobTypePage(list=items, total=total, page=page.page, size=page.size))


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_jobs(
    uow: UowDep,
    page: PageDep,
    job_type: TypeQuery = None,
    status: StatusQuery = None,
    service_key: ServiceQuery = None,
) -> ApiResponse:
    """统一作业列表（读平台监控投影）。

    Args:
        uow: 平台库工作单元。
        page: 分页参数。
        job_type: 作业类型筛选。
        status: 状态筛选。
        service_key: 提供方服务筛选。

    Returns:
        ApiResponse: 统一响应，data 为分页结果。
    """
    repository = JobMonitorRepository(cast("DbSession", uow.session))
    async with uow.begin():
        rows, total = await repository.page_filtered(
            page=page.page,
            size=page.size,
            job_type=job_type,
            status=status,
            service_key=service_key,
            tenant_id=current_tenant_context().tenant_id,
        )
    items = ConcurrentStableList(JobMonitorItem.model_validate(row) for row in rows)
    return ApiResponse.ok(JobMonitorPage(list=items, total=total, page=page.page, size=page.size))


@router.get("/{job_id}", dependencies=[_REQUIRE_QUERY])
async def get_job(uow: UowDep, job_id: int) -> ApiResponse:
    """作业详情（读平台监控投影）。

    Args:
        uow: 平台库工作单元。
        job_id: 作业标识。

    Returns:
        ApiResponse: 统一响应，data 为投影详情。

    Raises:
        JobNotFoundError: 投影中不存在（`71001`）。
    """
    repository = JobMonitorRepository(cast("DbSession", uow.session))
    async with uow.begin():
        record = await repository.get_by_job_id(job_id)
    if record is None:
        raise JobNotFoundError(f"作业不存在或投影尚未到达：{job_id}")
    return ApiResponse.ok(JobMonitorItem.model_validate(record))


@router.post("/{job_id}/cancel", dependencies=[_REQUIRE_MANAGE])
async def cancel_job(uow: UowDep, job_id: int, request: JobCancelRequest | None = None) -> ApiResponse:
    """取消作业（按投影服务键转发到目标服务）。

    Args:
        uow: 平台库工作单元。
        job_id: 作业标识。
        request: 取消原因（可选）。

    Returns:
        ApiResponse: 统一响应，data 为处理结果。

    Raises:
        JobNotFoundError: 投影中不存在（`71001`）。
        JobNotCancelableError: 终态不可取消（`71003`）。
    """
    service_key = await _service_key_of(uow, job_id)
    status = await _client().cancel(
        service_key=service_key,
        job_id=job_id,
        reason=None if request is None else request.reason,
        tenant_id=current_tenant_context().tenant_id,
    )
    return ApiResponse.ok(JobActionResponse(status=status))


@router.post("/{job_id}/retry", dependencies=[_REQUIRE_MANAGE])
async def retry_job(uow: UowDep, job_id: int) -> ApiResponse:
    """重试作业（仅 dead / failed；按投影服务键转发）。

    Args:
        uow: 平台库工作单元。
        job_id: 作业标识。

    Returns:
        ApiResponse: 统一响应，data 为处理结果。

    Raises:
        JobNotFoundError: 投影中不存在（`71001`）。
        JobNotRetryableError: 非 dead / failed 不可重试（`71004`）。
    """
    service_key = await _service_key_of(uow, job_id)
    status = await _client().retry(
        service_key=service_key, job_id=job_id, tenant_id=current_tenant_context().tenant_id
    )
    return ApiResponse.ok(JobActionResponse(status=status))


async def _service_key_of(uow: UnitOfWork, job_id: int) -> str:
    """取作业的提供方服务键（读投影）。

    Args:
        uow: 平台库工作单元。
        job_id: 作业标识。

    Returns:
        str: 服务键。

    Raises:
        JobNotFoundError: 投影中不存在（`71001`）。
    """
    repository = JobMonitorRepository(cast("DbSession", uow.session))
    async with uow.begin():
        record = await repository.get_by_job_id(job_id)
    if record is None:
        raise JobNotFoundError(f"作业不存在或投影尚未到达：{job_id}")
    return record.service_key
