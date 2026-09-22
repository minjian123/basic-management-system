"""租户自助占位路由：`/api/v1/tenants`（我的租户 / 切换 / 品牌）。

- 我的租户 `GET /tenants/mine` 与切换 `POST /tenants/switch` 需登录；品牌 `GET /tenants/brand` **免登录**
  （登录页需要品牌，按编码预览目标租户品牌，缺省取当前租户）。
- 当前租户编码取自租户解析链上下文（子域名 → 请求头 → token，优先级不变），经契约入参传入。
- 切换接口按需接幂等基座（02-25）：读 `Idempotency-Key` 头（缺失即跳过），作用域绑当前租户位，
  重复请求复用首次结果。
- 切换请求的租户编码由请求契约校验（空编码 → 参数错误 10001，经全局校验处理器统一收口）。
- 真实取数 / 令牌换发 / 品牌来源随认证与租户管理阶段，本路由只做参数校验与委托。
"""

from typing import Annotated

from fastapi import Depends, Header, Query

from bms_core.api.base import BaseRouter, require_auth
from bms_core.api.deps import get_idempotency_store, get_tenant, get_tenant_self_service
from bms_core.db.tenant import TenantContext
from bms_core.idempotency.base import IDEMPOTENCY_HEADER, IdempotencyStore, build_idempotency_key
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.tenant import (
    TenantBrandResponse,
    TenantSelfOverviewResponse,
    TenantSummaryResponse,
    TenantSwitchRequest,
    TenantSwitchResponse,
)
from bms_core.tenant.base import (
    BaseTenantSelfService,
    TenantBrand,
    TenantSelfOverview,
    TenantSummary,
    TenantSwitchResult,
)

router = BaseRouter(key="tenant", prefix="/tenants", tags=["tenant"])

ServiceDep = Annotated[BaseTenantSelfService, Depends(get_tenant_self_service)]
IdempotencyDep = Annotated[IdempotencyStore, Depends(get_idempotency_store)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
CodeQuery = Annotated[str | None, Query(description="租户编码（缺省当前租户）")]
IdempotencyKeyHeader = Annotated[
    str | None,
    Header(alias=IDEMPOTENCY_HEADER, description="幂等键（可选；重复切换复用首次结果）"),
]


def _summary_response(item: TenantSummary) -> TenantSummaryResponse:
    """把能力域租户摘要映射为路由响应契约（字段一一对应）。

    Args:
        item: 能力域租户摘要。

    Returns:
        TenantSummaryResponse: 路由响应契约。
    """
    return TenantSummaryResponse(
        id=item.id,
        name=item.name,
        code=item.code,
        logo=item.logo,
        role_name=item.role_name,
    )


def _overview_response(overview: TenantSelfOverview) -> TenantSelfOverviewResponse:
    """把能力域自助概览映射为路由响应契约。

    Args:
        overview: 能力域自助概览。

    Returns:
        TenantSelfOverviewResponse: 路由响应契约。
    """
    return TenantSelfOverviewResponse(
        tenants=[_summary_response(item) for item in overview.tenants],
        current_code=overview.current_code,
        multi_tenant=overview.multi_tenant,
    )


def _switch_response(result: TenantSwitchResult) -> TenantSwitchResponse:
    """把能力域切换结果映射为路由响应契约。

    Args:
        result: 能力域切换结果。

    Returns:
        TenantSwitchResponse: 路由响应契约。
    """
    return TenantSwitchResponse(
        tenant_code=result.tenant_code,
        db_key=result.db_key,
        applied=result.applied,
        mode=result.mode,
        reissue_token=result.reissue_token,
        token=result.token,
    )


def _brand_response(brand: TenantBrand) -> TenantBrandResponse:
    """把能力域品牌信息映射为路由响应契约。

    Args:
        brand: 能力域品牌信息。

    Returns:
        TenantBrandResponse: 路由响应契约。
    """
    return TenantBrandResponse(
        name=brand.name,
        logo=brand.logo,
        favicon=brand.favicon,
        primary_color=brand.primary_color,
        default_mode=brand.default_mode,
        login_bg=brand.login_bg,
        allow_user_accent=brand.allow_user_accent,
        disable_dark=brand.disable_dark,
    )


def current_code_of(tenant: TenantContext | None) -> str | None:
    """取解析链当前租户编码。

    Args:
        tenant: 请求级租户上下文（豁免路径为 None）。

    Returns:
        str | None: 当前租户编码；无上下文为空。
    """
    return tenant.tenant_code if tenant is not None else None


@router.get("/mine", dependencies=[Depends(require_auth)])
async def my_tenants(service: ServiceDep, tenant: TenantDep) -> ApiResponse:
    """取「我加入的租户」概览（当前租户取自解析链上下文）。

    Args:
        service: 租户自助基座。
        tenant: 解析链租户上下文。

    Returns:
        ApiResponse: 统一响应，data 为自助概览（`TenantSelfOverviewResponse`）。
    """
    overview = await service.my_tenants(current_code=current_code_of(tenant))
    return ApiResponse.ok(_overview_response(overview))


@router.post("/switch", dependencies=[Depends(require_auth)])
async def switch_tenant(
    service: ServiceDep,
    idempotency: IdempotencyDep,
    tenant: TenantDep,
    req: TenantSwitchRequest,
    idempotency_key: IdempotencyKeyHeader = None,
) -> ApiResponse:
    """切换到目标租户（可按幂等键复用首次结果）。

    Args:
        service: 租户自助基座。
        idempotency: 幂等基座（首次结果复用）。
        tenant: 解析链租户上下文（幂等键作用域位）。
        req: 切换请求。
        idempotency_key: 幂等键请求头（可选）。

    Returns:
        ApiResponse: 统一响应，data 为切换结果（`TenantSwitchResponse`）。
    """
    code = req.code
    if not idempotency_key:
        return ApiResponse.ok(_switch_response(await service.switch(code)))
    key = build_idempotency_key(key=idempotency_key, tenant=current_code_of(tenant))
    if not await idempotency.begin(key):
        payload = await idempotency.load(key)
        if payload is not None:
            return ApiResponse.ok(TenantSwitchResponse.model_validate(payload))
    result = await service.switch(code)
    await idempotency.save(key, result.model_dump(mode="json"))
    return ApiResponse.ok(_switch_response(result))


@router.get("/brand")
async def tenant_brand(service: ServiceDep, code: CodeQuery = None) -> ApiResponse:
    """取品牌信息（登录前可用；缺省当前租户）。

    Args:
        service: 租户自助基座。
        code: 租户编码（可选）。

    Returns:
        ApiResponse: 统一响应，data 为品牌信息（`TenantBrandResponse`）。
    """
    return ApiResponse.ok(_brand_response(await service.brand(code=code)))
