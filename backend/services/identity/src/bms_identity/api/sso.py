"""认证与身份服务端点：SSO 登录三端点（入口清单 / 授权跳转 / 回调闭环）。

- `GET /api/v1/auth/sso/providers`：公开；租户 = 上下文优先 + `tenant` 参数回落。
- `GET /api/v1/auth/sso/{idp_key}/authorize`：公开；生成流程状态并 `302` 外部授权端点。
- `GET /api/v1/auth/sso/{idp_key}/callback`：公开；**租户以 `state` 记录为权威**，闭环后
  `302 {success_redirect}?tenant=…` + refresh cookie；配置缺失时回退 JSON。
- 失败分支：配置了 `failure_redirect` → `302 {failure_redirect}?error={code}&message=…`（只取配置，
  防开放重定向）；否则抛 `BizError` 走统一 JSON 错误体（HTTP 随错误码）。
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from bms_core.api.base import BaseRouter
from bms_core.api.deps import (
    get_distributed_lock,
    get_idp_state_store,
    get_outbox_store,
    get_rate_limiter,
    get_realtime_publisher,
    get_service_client,
    get_session_security,
    get_session_store,
    get_tenant,
    get_tenant_source,
    get_user_token_issuer,
)
from bms_core.core.context import current_client_ip
from bms_core.core.exceptions import BizError, SsoProviderNotFoundError
from bms_core.db.registry import PLATFORM_DB_KEY, EngineRegistry
from bms_core.db.session import session_scope
from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.lock.base import BaseDistributedLock
from bms_core.oauth.user_token import BaseUserTokenIssuer
from bms_core.outbox.base import BaseOutboxStore
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BaseSessionSecurity
from bms_core.servicecall.base import BaseServiceClient
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.api.cookies import set_refresh_cookie
from bms_identity.schemas.sso import SsoAuthorizeInfo, SsoCallbackResult, SsoProviderList
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.provider_registry import ProviderRegistry
from bms_identity.services.session_issuer import build_session_issuer
from bms_identity.services.sso import SsoLoginResult, SsoService

router = BaseRouter(key="sso", prefix="/auth/sso", tags=["sso"], default_responses=False)

StateStoreDep = Annotated[BaseIdpStateStore, Depends(get_idp_state_store)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
LockDep = Annotated[BaseDistributedLock, Depends(get_distributed_lock)]
OutboxDep = Annotated[BaseOutboxStore, Depends(get_outbox_store)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
TenantSourceDep = Annotated[TenantLookup, Depends(get_tenant_source)]
IssuerDep = Annotated[BaseUserTokenIssuer, Depends(get_user_token_issuer)]
SecurityDep = Annotated[BaseSessionSecurity, Depends(get_session_security)]
StoreDep = Annotated[BaseSessionStore, Depends(get_session_store)]
PublisherDep = Annotated[BaseRealtimePublisher, Depends(get_realtime_publisher)]


async def _resolve_sso_tenant(
    tenant: str | None,
    context: TenantContext | None,
    source: TenantLookup,
) -> TenantContext:
    """解析 SSO 端点生效租户：上下文与参数不一致即 20051。

    Args:
        tenant: 查询参数租户编码（可选）。
        context: 请求上下文（子域名 / `X-Tenant-ID`）租户。
        source: 租户源（按编码校验存在）。

    Returns:
        TenantContext: 生效租户上下文。

    Raises:
        SsoProviderNotFoundError: 参数与上下文租户不一致（20051/404）。
        TenantNotFoundError: 无任何租户来源（既有，与 refresh 同口径）。
    """
    if tenant and context is not None and tenant != context.code:
        raise SsoProviderNotFoundError()
    if tenant:
        resolved = await source.by_code(tenant)
    elif context is not None:
        resolved = context
    else:
        raise TenantNotFoundError("未提供租户标识")
    if resolved.tenant_id is None:
        raise TenantNotFoundError("租户缺少主键标识")
    return resolved


def _build_service(
    *,
    request: Request,
    state_store: BaseIdpStateStore,
    limiter: BaseRateLimiter,
    client: BaseServiceClient,
    lock: BaseDistributedLock,
    outbox_store: BaseOutboxStore,
) -> SsoService:
    """构造 SSO 服务（请求级能力域 + 配置）。

    Args:
        request: 请求对象（取应用配置）。
        state_store: 流程状态存储。
        limiter: 限流基座。
        client: 服务间调用客户端。
        lock: 分布式锁（JIT 临界区）。
        outbox_store: 事务性发件箱（JIT 事件）。

    Returns:
        SsoService: SSO 编排服务。
    """
    settings = request.app.state.settings
    return SsoService(
        state_store=state_store,
        rate_limiter=limiter,
        org_client=OrgCredentialClient(client),
        provider_registry=ProviderRegistry(callback_base_url=settings.sso.callback_base_url),
        sso_settings=settings.sso,
        lock=lock,
        outbox_store=outbox_store,
    )


@router.get("/providers")
async def providers(
    request: Request,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    state_store: StateStoreDep,
    limiter: LimiterDep,
    lock: LockDep,
    outbox_store: OutboxDep,
    client: ClientDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> ApiResponse[SsoProviderList]:
    """可用 IdP 入口清单（仅 `enabled`；无启用 IdP 返回空列表）。

    Args:
        request: 请求对象。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        state_store: 流程状态存储（保持服务构造一致）。
        limiter: 限流基座（保持服务构造一致）。
        lock: 分布式锁（保持服务构造一致）。
        outbox_store: 事务性发件箱（保持服务构造一致）。
        client: 服务间调用客户端（保持服务构造一致）。
        tenant: 租户编码（可选）。

    Returns:
        ApiResponse: 统一响应，data 为 `SsoProviderList`。
    """
    context = await _resolve_sso_tenant(tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=context.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            state_store=state_store,
            limiter=limiter,
            client=client,
            lock=lock,
            outbox_store=outbox_store,
        )
        items = await service.list_providers(context.code, session)
    return ApiResponse.ok(SsoProviderList(items=items))


@router.get("/{idp_key}/authorize")
async def authorize(
    request: Request,
    idp_key: str,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    state_store: StateStoreDep,
    limiter: LimiterDep,
    lock: LockDep,
    outbox_store: OutboxDep,
    client: ClientDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> Response:
    """生成流程状态并 `302` 到外部授权端点。

    Args:
        request: 请求对象。
        idp_key: 租户内 IdP 标识（路由参数）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        state_store: 流程状态存储。
        limiter: 限流基座。
        lock: 分布式锁（保持服务构造一致）。
        outbox_store: 事务性发件箱（保持服务构造一致）。
        client: 服务间调用客户端。
        tenant: 租户编码（可选）。

    Returns:
        Response: `302` 跳转外部授权端点。

    Raises:
        SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
        SsoProviderUnavailableError: IdP 配置缺失 / 发现失败（20053/503）。
        RateLimitError: 限流命中（10005/429）。
    """
    context = await _resolve_sso_tenant(tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=context.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            state_store=state_store,
            limiter=limiter,
            client=client,
            lock=lock,
            outbox_store=outbox_store,
        )
        url = await service.authorize(
            idp_key,
            tenant_id=str(context.tenant_id),
            tenant_code=context.code,
            ip=current_client_ip.get(),
            session=session,
        )
    return RedirectResponse(url, status_code=302)


@router.get("/{idp_key}/authorize-url")
async def authorize_url(
    request: Request,
    idp_key: str,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    state_store: StateStoreDep,
    limiter: LimiterDep,
    lock: LockDep,
    outbox_store: OutboxDep,
    client: ClientDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> ApiResponse[SsoAuthorizeInfo]:
    """取外部授权 URL（JSON 形态；供前端渲染二维码 / 初始化平台内嵌登录组件）。

    Args:
        request: 请求对象。
        idp_key: 租户内 IdP 标识（路由参数）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        state_store: 流程状态存储。
        limiter: 限流基座。
        lock: 分布式锁（保持服务构造一致）。
        outbox_store: 事务性发件箱（保持服务构造一致）。
        client: 服务间调用客户端。
        tenant: 租户编码（可选）。

    Returns:
        ApiResponse: 统一响应，data 为 `SsoAuthorizeInfo`（授权 URL / 流程状态 / 有效期）。

    Raises:
        SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
        SsoProviderUnavailableError: IdP 配置缺失 / 发现失败（20053/503）。
        EnterpriseIdpError: 企微 / 钉钉专用失败（20057~20062）。
        RateLimitError: 限流命中（10005/429）。
    """
    context = await _resolve_sso_tenant(tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=context.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            state_store=state_store,
            limiter=limiter,
            client=client,
            lock=lock,
            outbox_store=outbox_store,
        )
        result = await service.authorize_info(
            idp_key,
            tenant_id=str(context.tenant_id),
            tenant_code=context.code,
            ip=current_client_ip.get(),
            session=session,
        )
    return ApiResponse.ok(
        SsoAuthorizeInfo(
            authorize_url=result.authorize_url,
            state=result.state,
            expires_in=result.expires_in,
        )
    )


@router.get("/{idp_key}/callback")
async def callback(
    request: Request,
    idp_key: str,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    state_store: StateStoreDep,
    limiter: LimiterDep,
    lock: LockDep,
    outbox_store: OutboxDep,
    client: ClientDep,
    issuer: IssuerDep,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    state: Annotated[str | None, Query(description="IdP 回传流程状态")] = None,
    code: Annotated[str | None, Query(description="IdP 回传授权码（OIDC）")] = None,
    ticket: Annotated[str | None, Query(description="IdP 回传服务票据（CAS）")] = None,
    error: Annotated[str | None, Query(description="IdP 回传错误（如 access_denied）")] = None,
) -> Response:
    """回调闭环：`state` 一次性消费 → 换码 / 票据校验 → 映射（未命中 JIT 建号）→ 签发会话 → `302` 前端。

    Args:
        request: 请求对象。
        idp_key: 回调路径中的 IdP 标识。
        tenant_ctx: 请求上下文租户（有则与 `state` 记录交叉校验）。
        tenant_source: 租户源（按 `state` 记录租户定位库键）。
        state_store: 流程状态存储。
        limiter: 限流基座。
        lock: 分布式锁（JIT 临界区）。
        outbox_store: 事务性发件箱（JIT 事件）。
        client: 服务间调用客户端。
        issuer: 用户双 token 签发者。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        state: IdP 回传流程状态。
        code: IdP 回传授权码（OIDC）。
        ticket: IdP 回传服务票据（CAS；与 `code` 归一）。
        error: IdP 回传错误。

    Returns:
        Response: 成功 `302 {success_redirect}?tenant=…` + refresh cookie（未配置回退 200 JSON）；
        失败 `302 {failure_redirect}?error=&message=`（未配置抛 `BizError`）。
    """
    settings = request.app.state.settings
    ip = current_client_ip.get()
    user_agent = request.headers.get("user-agent")
    service = _build_service(
        request=request,
        state_store=state_store,
        limiter=limiter,
        client=client,
        lock=lock,
        outbox_store=outbox_store,
    )
    try:
        flow = await service.consume_flow(
            state or "",
            idp_key=idp_key,
            tenant_code=tenant_ctx.code if tenant_ctx is not None else None,
            ip=ip,
        )
        tenant = await tenant_source.by_id(flow.tenant_id)
        registry: EngineRegistry = request.app.state.engine_registry
        factory = request.app.state.session_factory
        async with (
            session_scope(registry, db_key=tenant.db_key, factory=factory) as session,
            session_scope(registry, db_key=PLATFORM_DB_KEY, factory=factory) as platform_session,
        ):
            session_issuer = build_session_issuer(
                session=session,
                uow=DbUnitOfWork(session),
                user_token_issuer=issuer,
                session_security=security,
                session_store=store,
                session_settings=settings.session,
                realtime_publisher=publisher,
            )
            result = await service.callback(
                flow,
                idp_key=idp_key,
                code=code or ticket,
                error=error,
                ip=ip,
                user_agent=user_agent,
                session=session,
                platform_session=platform_session,
                session_issuer=session_issuer,
                state=state or "",
            )
    except BizError as exc:
        return _failure_response(settings.sso.failure_redirect, exc)
    return _success_response(request, result)


def _success_response(request: Request, result: SsoLoginResult) -> Response:
    """成功响应：跳转地址只取配置；未配置回退 JSON（附 refresh cookie）。

    Args:
        request: 请求对象（取配置 / 下发 cookie）。
        result: 登录结果。

    Returns:
        Response: `302` 跳转 + cookie，或 200 JSON + cookie。
    """
    payload = ApiResponse.ok(SsoCallbackResult(tenant=result.tenant_code))
    target = request.app.state.settings.sso.success_redirect
    if target:
        response: Response = RedirectResponse(
            _with_query(target, urlencode({"tenant": result.tenant_code})),
            status_code=302,
        )
    else:
        response = JSONResponse(content=payload.model_dump(mode="json"), status_code=200)
    set_refresh_cookie(response, request, result.issued.refresh_token, result.issued.refresh_expires_in)
    return response


def _failure_response(target: str, exc: BizError) -> Response:
    """失败响应：配置了失败跳转则 `302`（错误码 + 消息），否则抛统一 JSON 错误体。

    Args:
        target: `[sso].failure_redirect` 配置值。
        exc: 业务异常。

    Returns:
        Response: `302` 失败跳转。

    Raises:
        BizError: 未配置失败跳转时原样抛出（走统一错误体）。
    """
    if not target:
        raise exc
    query = urlencode({"error": exc.code, "message": exc.message or f"error.{exc.code}"})
    return RedirectResponse(_with_query(target, query), status_code=302)


def _with_query(target: str, query: str) -> str:
    """拼接跳转地址查询串（保留既有查询参数）。

    Args:
        target: 配置的跳转地址。
        query: 追加查询串。

    Returns:
        str: 拼接后的地址。
    """
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{query}"
