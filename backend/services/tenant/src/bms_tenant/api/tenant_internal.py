"""租户内部契约：模块状态 / 配额校验·占用·释放（服务间，`require_service`；任务 `04_01`）。

- 模块状态：各服务模块门禁回源（`GET /modules/status`）；
- 配额：platform（创建 / 删除用户）与 file（上传完成）在业务动作前后调用；
- 无配额行视为不限制（平台租户与未配置租户平滑）。
"""

from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, require_service
from bms_core.db.session import DbSession, get_platform_read_db, get_platform_write_db
from bms_core.schemas.common import ApiResponse
from bms_tenant.schemas.tenant_admin import (
    ModuleStatusResponse,
    QuotaConsumeRequest,
    QuotaReleaseRequest,
    QuotaResult,
)
from bms_tenant.services.tenant_module import ModuleCatalog, TenantModuleService
from bms_tenant.services.tenant_quota import TenantQuotaService

router = BaseRouter(
    key="tenant_internal",
    prefix="/tenant/internal",
    tags=["tenant-internal"],
    dependencies=[Depends(require_service())],
)

ReadDep = Annotated[DbSession, Depends(get_platform_read_db)]
WriteDep = Annotated[DbSession, Depends(get_platform_write_db)]
TenantIdQuery = Annotated[int, Query(description="租户主键")]


@router.get("/modules/status")
async def module_status(
    request: Request, session: ReadDep, tenant_id: TenantIdQuery
) -> ApiResponse[ModuleStatusResponse]:
    """取租户模块状态集（模块门禁回源）。

    Args:
        request: 请求对象。
        session: 平台库只读会话。
        tenant_id: 租户主键。

    Returns:
        ApiResponse: 统一响应（data 为状态集）。
    """
    service = TenantModuleService(
        session=session,
        catalog=ModuleCatalog(client=request.app.state.service_client, cache=None),
    )
    return ApiResponse.ok(await service.status(tenant_id))


@router.post("/quotas/check")
async def check_quota(req: QuotaConsumeRequest, session: ReadDep, request: Request) -> ApiResponse[QuotaResult]:
    """校验配额（不写；超限 82005）。

    Args:
        req: 校验请求。
        session: 平台库只读会话。
        request: 请求对象（取配置）。

    Returns:
        ApiResponse: 统一响应（data 为校验结果）。
    """
    service = TenantQuotaService(session, request.app.state.settings)
    return ApiResponse.ok(await service.check(req.tenant_id, req.quota_key, req.amount))


@router.post("/quotas/consume")
async def consume_quota(req: QuotaConsumeRequest, session: WriteDep, request: Request) -> ApiResponse[QuotaResult]:
    """原子占用配额（超限 82005）。

    Args:
        req: 占用请求。
        session: 平台库写会话。
        request: 请求对象（取配置）。

    Returns:
        ApiResponse: 统一响应（data 为占用结果）。
    """
    service = TenantQuotaService(session, request.app.state.settings)
    result = await service.consume(req.tenant_id, req.quota_key, req.amount)
    await session.commit()
    return ApiResponse.ok(result)


@router.post("/quotas/release")
async def release_quota(req: QuotaReleaseRequest, session: WriteDep, request: Request) -> ApiResponse[QuotaResult]:
    """释放配额用量（下限 0）。

    Args:
        req: 释放请求。
        session: 平台库写会话。
        request: 请求对象（取配置）。

    Returns:
        ApiResponse: 统一响应（data 为释放结果）。
    """
    service = TenantQuotaService(session, request.app.state.settings)
    result = await service.release(req.tenant_id, req.quota_key, req.amount)
    await session.commit()
    return ApiResponse.ok(result)
