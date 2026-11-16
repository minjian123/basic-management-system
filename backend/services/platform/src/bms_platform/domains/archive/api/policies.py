"""归档策略端点：`/api/v1/archive/policies`（CRUD + 手动触发）。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.api.deps import get_platform_uow
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.idempotency.base import IDEMPOTENCY_HEADER
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission
from bms_core.models.platform.archive import SysArchivePolicy
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.domains.archive.repositories.policy import ArchivePolicyRepository
from bms_platform.domains.archive.schemas.archive import (
    ArchiveDeleteResult,
    ArchivePolicyCreateRequest,
    ArchivePolicyItem,
    ArchivePolicyPage,
    ArchivePolicyUpdateRequest,
    ArchiveTriggerResult,
)
from bms_platform.domains.archive.services.policy import ArchivePolicyService
from bms_platform.jobs import build_runner

__all__ = ["router"]

router = BaseRouter(
    key="archive_policies",
    prefix="/archive/policies",
    tags=["archive"],
    dependencies=[Depends(require_auth)],
)

_REQUIRE_QUERY = Depends(require_permission("archive:query"))
_REQUIRE_MANAGE = Depends(require_permission("archive:manage"))
_REQUIRE_TRIGGER = Depends(require_permission("archive:trigger"))

UowDep = Annotated[UnitOfWork, Depends(get_platform_uow)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
TableQuery = Annotated[str | None, Query(description="表名筛选")]
StatusQuery = Annotated[str | None, Query(description="状态筛选（enabled / disabled）")]
IdempotencyKeyHeader = Annotated[str | None, Header(alias=IDEMPOTENCY_HEADER, description="幂等键（手动触发去重）")]

ARCHIVE_RUN_JOB = "platform.archive.run"


def _service(uow: UnitOfWork) -> ArchivePolicyService:
    """构造策略服务。"""
    return ArchivePolicyService(cast("DbSession", uow.session), get_settings())


def _page(items: ConcurrentStableList[SysArchivePolicy], total: int, page: int, size: int) -> ArchivePolicyPage:
    """构造分页响应。"""
    return ArchivePolicyPage(
        list=ConcurrentStableList(ArchivePolicyItem.model_validate(item) for item in items),
        total=total,
        page=page,
        size=size,
    )


@router.get("", dependencies=[_REQUIRE_QUERY])
async def list_policies(
    uow: UowDep, page: PageDep, table_name: TableQuery = None, status: StatusQuery = None
) -> ApiResponse[ArchivePolicyPage]:
    """归档策略分页查询。

    Args:
        uow: 平台库工作单元。
        page: 分页参数。
        table_name: 表名筛选。
        status: 状态筛选。

    Returns:
        ApiResponse[ArchivePolicyPage]: 分页结果。
    """
    service = _service(uow)
    meta, rows = await service.list(page=page.page, size=page.size, table_name=table_name, status=status)
    return ApiResponse.ok(_page(rows, int(str(meta["total"])), page.page, page.size))


@router.post("", dependencies=[_REQUIRE_MANAGE])
async def create_policy(request: ArchivePolicyCreateRequest, uow: UowDep) -> ApiResponse[ArchivePolicyItem]:
    """新增归档策略。

    Args:
        request: 新增请求。
        uow: 平台库工作单元。

    Returns:
        ApiResponse[ArchivePolicyItem]: 已创建策略。
    """
    service = _service(uow)
    async with uow.begin():
        policy = await service.create(request)
    return ApiResponse.ok(ArchivePolicyItem.model_validate(policy))


@router.put("/{policy_id}", dependencies=[_REQUIRE_MANAGE])
async def update_policy(
    policy_id: int, request: ArchivePolicyUpdateRequest, uow: UowDep
) -> ApiResponse[ArchivePolicyItem]:
    """修改归档策略。

    Args:
        policy_id: 策略主键。
        request: 修改请求。
        uow: 平台库工作单元。

    Returns:
        ApiResponse[ArchivePolicyItem]: 更新后策略。
    """
    service = _service(uow)
    async with uow.begin():
        policy = await service.update(policy_id, request)
    return ApiResponse.ok(ArchivePolicyItem.model_validate(policy))


@router.delete("/{policy_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_policy(policy_id: int, uow: UowDep) -> ApiResponse[ArchiveDeleteResult]:
    """删除归档策略（仅停用且未执行中）。

    Args:
        policy_id: 策略主键。
        uow: 平台库工作单元。

    Returns:
        ApiResponse[ArchiveDeleteResult]: 删除结果。
    """
    service = _service(uow)
    async with uow.begin():
        await service.delete(policy_id)
    return ApiResponse.ok(ArchiveDeleteResult(id=policy_id, deleted=True))


@router.post("/{policy_id}/trigger", dependencies=[_REQUIRE_TRIGGER])
async def trigger_policy(
    policy_id: int,
    uow: UowDep,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse[ArchiveTriggerResult]:
    """手动触发一次归档（全量执行该策略）。

    Args:
        policy_id: 策略主键。
        uow: 平台库工作单元。
        idempotency_key: 幂等键（请求头 Idempotency-Key）。

    Returns:
        ApiResponse[ArchiveTriggerResult]: 作业主键。
    """
    session = cast("DbSession", uow.session)
    policy = await ArchivePolicyRepository(session).get(policy_id)
    if policy is None:
        from bms_core.core.exceptions import ArchiveDataNotFoundError

        raise ArchiveDataNotFoundError(f"归档策略不存在：{policy_id}")
    if policy.status != "enabled":
        from bms_core.core.exceptions import ArchivePolicyDisabledError

        raise ArchivePolicyDisabledError("归档策略已停用，不可手动触发")
    in_transaction = getattr(session, "in_transaction", None)
    if callable(in_transaction) and in_transaction():
        await session.rollback()
    runner: JobRunner = build_runner()
    submission = JobSubmission(
        job_type=ARCHIVE_RUN_JOB,
        payload=ConcurrentStableDict({"policy_id": str(policy_id)}),
        max_attempts=1,
        idempotency_key=idempotency_key,
    )
    async with uow.begin():
        record = await runner.submit(session, submission, tenant_id=None)
    result = ArchiveTriggerResult(job_id=record.id, policy_id=policy_id)
    return ApiResponse.ok(result)
