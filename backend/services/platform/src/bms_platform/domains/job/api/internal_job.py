"""作业中心服务内部面：`/api/v1/jobs/internal`（提交 / 本地详情 / 取消 / 重试）。

- **身份**：服务间调用（服务 JWT）；租户链通过服务 JWT 的 `tenant_id` 解析租户库；
- **作业落本服务库**：提交在目标服务自己的 `sys_job` 写入，执行由本服务 worker 承担；
- **错误码**：`71001` 不存在、`71002` 类型未声明、`71003` 不可取消、`71004` 不可重试、`71005` 负载非法。
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_uow
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.exceptions import (
    JobNotCancelableError,
    JobNotFoundError,
    JobNotRetryableError,
)
from bms_core.db.session import DbSession
from bms_core.db.tenant import current_tenant_context
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.jobs import store
from bms_core.jobs.spec import JobSubmission
from bms_core.schemas.common import ApiResponse
from bms_platform.domains.job.schemas.job import (
    JobActionResponse,
    JobCancelRequest,
    JobInternalItem,
    JobSubmitRequest,
)
from bms_platform.jobs import build_runner

router = BaseRouter(
    key="job_internal",
    prefix="/jobs/internal",
    tags=["job"],
    dependencies=[Depends(require_auth)],
)

UowDep = Annotated[UnitOfWork, Depends(get_uow)]


@router.post("")
async def submit_job(uow: UowDep, request: JobSubmitRequest) -> ApiResponse:
    """提交本服务声明的作业类型。

    Args:
        uow: 租户库工作单元。
        request: 提交请求。

    Returns:
        ApiResponse: 统一响应，data 含作业标识。
    """
    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {str(key): value for key, value in request.payload.items()}
    )
    tenant = current_tenant_context()
    async with uow.begin():
        record = await build_runner().submit(
            cast("DbSession", uow.session),
            JobSubmission(
                job_type=request.job_type,
                payload=payload,
                priority=request.priority,
                idempotency_key=request.idempotency_key,
                max_attempts=request.max_attempts,
                payload_version=request.payload_version or "1.0.0",
            ),
            tenant_id=tenant.tenant_id,
        )
    return ApiResponse.ok({"job_id": str(record.id)})


@router.get("/{job_id}")
async def get_job(uow: UowDep, job_id: int) -> ApiResponse:
    """本地作业详情（含结果与错误摘要）。

    Args:
        uow: 租户库工作单元。
        job_id: 作业标识。

    Returns:
        ApiResponse: 统一响应，data 为本地详情。

    Raises:
        JobNotFoundError: 作业不存在（`71001`）。
    """
    async with uow.begin():
        record = await store.get_job(cast("DbSession", uow.session), job_id)
    if record is None:
        raise JobNotFoundError(f"作业不存在：{job_id}")
    return ApiResponse.ok(
        JobInternalItem(
            job_id=int(record.id),
            job_type=record.job_type,
            status=record.status,
            tenant_id=record.tenant_id,
            progress_done=int(record.progress_done),
            progress_total=record.progress_total,
            attempts=int(record.attempts),
            max_attempts=int(record.max_attempts),
            error=record.error,
            result=record.result,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )
    )


@router.post("/{job_id}/cancel")
async def cancel_job(uow: UowDep, job_id: int, request: JobCancelRequest | None = None) -> ApiResponse:
    """本地取消作业。

    Args:
        uow: 租户库工作单元。
        job_id: 作业标识。
        request: 取消原因（可选）。

    Returns:
        ApiResponse: 统一响应，data 为处理结果。

    Raises:
        JobNotFoundError: 作业不存在（`71001`）。
        JobNotCancelableError: 终态不可取消（`71003`）。
    """
    async with uow.begin():
        status = await build_runner().cancel(
            cast("DbSession", uow.session), job_id, reason=None if request is None else request.reason
        )
    if status == "missing":
        raise JobNotFoundError(f"作业不存在：{job_id}")
    if status == "terminal":
        raise JobNotCancelableError(f"作业已处终态，不可取消：{job_id}")
    return ApiResponse.ok(JobActionResponse(status=status))


@router.post("/{job_id}/retry")
async def retry_job(uow: UowDep, job_id: int) -> ApiResponse:
    """本地重试作业（仅 dead / failed）。

    Args:
        uow: 租户库工作单元。
        job_id: 作业标识。

    Returns:
        ApiResponse: 统一响应，data 为处理结果。

    Raises:
        JobNotFoundError: 作业不存在（`71001`）。
        JobNotRetryableError: 非 dead / failed 不可重试（`71004`）。
    """
    async with uow.begin():
        status = await build_runner().retry(cast("DbSession", uow.session), job_id)
    if status == "missing":
        raise JobNotFoundError(f"作业不存在：{job_id}")
    if status != "retried":
        raise JobNotRetryableError(f"作业状态不可重试：{job_id}")
    return ApiResponse.ok(JobActionResponse(status=status))
