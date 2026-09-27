"""认证与身份服务端点：外部 IdP 配置管理（`/api/v1/idp/providers`）。

- 鉴权：`require_auth` + `require_permission("idp:manage")`（RBAC 前权限基座为 Null = 超管口径）。
- 数据源：identity 服务租户库 `sys_identity_provider`；响应 `config` 经脱敏（密钥引用不返明文）。
- 连通性测试：已保存行 `GET /{id}/test` 与草稿 `POST /test`（不落库）；不可达统一 `20066/502`（`data` 携结果）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path, Request

from bms_core.api.base import AuthContext, BaseRouter, page_query, require_auth
from bms_core.api.deps import get_audit_capturer, get_rate_limiter, get_tenant
from bms_core.audit.base import AuditCapturer
from bms_core.core.exceptions import AuthError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import TenantContext
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.idp.base import IdpProbeResult
from bms_core.permission.base import require_permission
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery, BasePageResponse
from bms_identity.schemas.identity_provider import (
    IdpProviderCreateRequest,
    IdpProviderItem,
    IdpProviderStatusRequest,
    IdpProviderTestRequest,
    IdpProviderTestResult,
    IdpProviderUpdateRequest,
)
from bms_identity.services.identity_providers import IdentityProviderService
from bms_identity.services.provider_registry import ProviderRegistry

router = BaseRouter(
    key="idp_providers",
    prefix="/idp/providers",
    tags=["idp-providers"],
    dependencies=[Depends(require_auth), Depends(require_permission("idp:manage"))],
)

TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
AuthDep = Annotated[AuthContext, Depends(require_auth)]
PageDep = Annotated[BasePageQuery, Depends(page_query)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
AuditDep = Annotated[AuditCapturer, Depends(get_audit_capturer)]
IdPath = Annotated[int, Path(description="IdP 配置主键")]


def _require_tenant(tenant: TenantContext | None) -> TenantContext:
    """取生效租户（缺失即认证失败）。

    Args:
        tenant: 请求上下文租户。

    Returns:
        TenantContext: 生效租户。

    Raises:
        AuthError: 缺少租户标识（20001/401）。
    """
    if tenant is None:  # pragma: no cover - 租户依赖恒回落演示租户，防御性兜底
        raise AuthError("缺少租户标识")
    return tenant


def _registry(request: Request) -> ProviderRegistry:
    """构造请求级 IdP 实例桥接（连通性测试）。

    Args:
        request: 请求对象（取应用配置）。

    Returns:
        ProviderRegistry: 实例桥接。
    """
    return ProviderRegistry(callback_base_url=request.app.state.settings.sso.callback_base_url)


@router.post("")
async def create_provider(
    request: Request,
    req: IdpProviderCreateRequest,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderItem]:
    """新建 IdP 配置。

    Args:
        request: 请求对象。
        req: 新建请求。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位。
        limiter: 限流基座（保持服务构造一致）。

    Returns:
        ApiResponse: 统一响应，data 为新建项（config 脱敏）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        row = await service.create(
            name=req.name,
            idp_key=req.idp_key,
            type=req.type,
            icon=req.icon,
            config=req.config,
            status=req.status,
            sort=req.sort,
            actor=auth.user_id,
        )
        item = service.item(row)
    return ApiResponse.ok(item)


@router.get("")
async def list_providers(
    request: Request,
    tenant_ctx: TenantDep,
    audit: AuditDep,
    limiter: LimiterDep,
    query: PageDep,
    status: str | None = None,
    type: str | None = None,
    name: str | None = None,
) -> ApiResponse[BasePageResponse[IdpProviderItem]]:
    """IdP 配置分页列表（可筛选 status / type / name）。

    Args:
        request: 请求对象。
        tenant_ctx: 请求上下文租户。
        audit: 审计捕获占位。
        limiter: 限流基座。
        query: 分页请求。
        status: 状态过滤（可选）。
        type: 协议类型过滤（可选）。
        name: 名称模糊过滤（可选）。

    Returns:
        ApiResponse: 统一响应，data 为分页 IdP 项。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        rows, total = await service.list(query, status=status, type=type, name=name)
        items = [service.item(row) for row in rows]
    return ApiResponse.ok(BasePageResponse[IdpProviderItem](list=items, total=total, page=query.page, size=query.size))


@router.post("/test")
async def test_draft_provider(
    request: Request,
    req: IdpProviderTestRequest,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderTestResult]:
    """草稿连通性测试（不落库）。

    Args:
        request: 请求对象。
        req: 草稿测试请求。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位（保持服务构造一致）。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为测试结果（可达）。

    Raises:
        IdpConfigInvalidError: 配置非法（20064/400）。
        IdpTestFailedError: 不可达 / 不可探测（20066/502）。
        RateLimitError: 限流命中（10005/429）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        result = await service.test_draft(
            type=req.type,
            config=req.config,
            idp_key=req.idp_key,
            tenant=tenant.tenant_code,
            actor=auth.user_id,
        )
    return ApiResponse.ok(_probe_result(result))


@router.get("/{provider_id}")
async def get_provider(
    request: Request,
    provider_id: IdPath,
    tenant_ctx: TenantDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderItem]:
    """IdP 配置详情。

    Args:
        request: 请求对象。
        provider_id: 主键。
        tenant_ctx: 请求上下文租户。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为详情项（config 脱敏）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        row = await service.get(provider_id)
        item = service.item(row)
    return ApiResponse.ok(item)


@router.put("/{provider_id}")
async def update_provider(
    request: Request,
    req: IdpProviderUpdateRequest,
    provider_id: IdPath,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderItem]:
    """修改 IdP 配置（`type` / `idp_key` 不可改）。

    Args:
        request: 请求对象。
        req: 修改请求。
        provider_id: 主键。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为更新后项（config 脱敏）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        row = await service.update(
            provider_id,
            name=req.name,
            icon=req.icon,
            config=req.config,
            sort=req.sort,
            actor=auth.user_id,
        )
        item = service.item(row)
    return ApiResponse.ok(item)


@router.post("/{provider_id}/status")
async def set_provider_status(
    request: Request,
    req: IdpProviderStatusRequest,
    provider_id: IdPath,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderItem]:
    """启停 IdP 配置。

    Args:
        request: 请求对象。
        req: 启停请求。
        provider_id: 主键。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为更新后项。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        row = await service.set_status(provider_id, req.status, actor=auth.user_id)
        item = service.item(row)
    return ApiResponse.ok(item)


@router.delete("/{provider_id}")
async def delete_provider(
    request: Request,
    provider_id: IdPath,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[dict[str, object]]:
    """软删除 IdP 配置。

    Args:
        request: 请求对象。
        provider_id: 主键。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为空对象。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        await service.delete(provider_id, actor=auth.user_id)
    return ApiResponse.ok({})


@router.get("/{provider_id}/test")
async def test_saved_provider(
    request: Request,
    provider_id: IdPath,
    tenant_ctx: TenantDep,
    auth: AuthDep,
    audit: AuditDep,
    limiter: LimiterDep,
) -> ApiResponse[IdpProviderTestResult]:
    """已保存行连通性测试。

    Args:
        request: 请求对象。
        provider_id: 主键。
        tenant_ctx: 请求上下文租户。
        auth: 登录态身份（操作者）。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        ApiResponse: 统一响应，data 为测试结果（可达）。

    Raises:
        IdpNotFoundError: 不存在（20063/404）。
        IdpConfigInvalidError: 存量配置非法（20064/400）。
        IdpTestFailedError: 不可达 / 不可探测（20066/502）。
        RateLimitError: 限流命中（10005/429）。
    """
    tenant = _require_tenant(tenant_ctx)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=tenant.db_key, factory=request.app.state.session_factory) as session:
        service = _build(request, session, audit, limiter)
        result = await service.test_saved(provider_id, tenant=tenant.tenant_code, actor=auth.user_id)
    return ApiResponse.ok(_probe_result(result))


def _build(
    request: Request,
    session: DbSession,
    audit: AuditCapturer,
    limiter: BaseRateLimiter,
) -> IdentityProviderService:
    """构造管理面服务（会话已开启）。

    Args:
        request: 请求对象（取应用配置）。
        session: 租户库会话。
        audit: 审计捕获占位。
        limiter: 限流基座。

    Returns:
        IdentityProviderService: 管理面服务。
    """
    return IdentityProviderService(
        session=session,
        uow=DbUnitOfWork(session),
        audit=audit,
        rate_limiter=limiter,
        provider_registry=_registry(request),
        idp_manage=request.app.state.settings.idp_manage,
    )


def _probe_result(result: IdpProbeResult) -> IdpProviderTestResult:
    """探测结果 → 响应 DTO。

    Args:
        result: 探测结果。

    Returns:
        IdpProviderTestResult: 响应项。
    """
    return IdpProviderTestResult(
        reachable=result.reachable,
        protocol=result.protocol,
        status=result.status,
        detail=result.detail,
    )
