"""认证与身份服务端点：自助找回密码（`/api/v1/auth/forgot-password` / `/reset-password`）。

- **免登录**：找回用于登录前场景，与 `/auth/login`、`/captcha/*` 同口径；经网关公开路径放行。
- **编排**：一律委托 `PasswordResetService`（限流 / 验证码 / token 一次性存取 / 通知占位 / 改密 / 会话全失效）。
- **防枚举**：发起成功路径恒 `{sent: true}`；详情见任务 03_06 详细设计 §3.4。
"""

from typing import Annotated

from fastapi import Depends, Request

from bms_core.api.base import BaseRouter
from bms_core.api.deps import (
    get_captcha,
    get_idp_state_store,
    get_notifier,
    get_rate_limiter,
    get_realtime_publisher,
    get_service_client,
    get_session_security,
    get_session_store,
    get_tenant,
    get_tenant_source,
)
from bms_core.captcha.base import BaseCaptcha
from bms_core.core.context import current_client_ip
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import TenantContext, TenantLookup
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.notify.base import BaseNotifier
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BaseSessionSecurity
from bms_core.servicecall.base import BaseServiceClient
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.api.tenancy import resolve_request_tenant
from bms_identity.schemas.password_reset import (
    PasswordForgotRequest,
    PasswordForgotResult,
    PasswordResetRequest,
    PasswordResetResult,
)
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.password_reset import PasswordResetService
from bms_identity.services.session import SessionService

router = BaseRouter(key="identity_password_reset", prefix="/auth", tags=["auth"])

CaptchaDep = Annotated[BaseCaptcha, Depends(get_captcha)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
StateStoreDep = Annotated[BaseIdpStateStore, Depends(get_idp_state_store)]
NotifierDep = Annotated[BaseNotifier, Depends(get_notifier)]
SecurityDep = Annotated[BaseSessionSecurity, Depends(get_session_security)]
StoreDep = Annotated[BaseSessionStore, Depends(get_session_store)]
PublisherDep = Annotated[BaseRealtimePublisher, Depends(get_realtime_publisher)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
TenantSourceDep = Annotated[TenantLookup, Depends(get_tenant_source)]


def _build_service(
    *,
    request: Request,
    session: DbSession,
    captcha: BaseCaptcha,
    limiter: BaseRateLimiter,
    client: BaseServiceClient,
    state_store: BaseIdpStateStore,
    notifier: BaseNotifier,
    security: BaseSessionSecurity,
    store: BaseSessionStore,
    publisher: BaseRealtimePublisher,
) -> PasswordResetService:
    """构造找回密码服务（请求级会话 + 各能力域 + 配置）。

    Args:
        request: 请求对象（取应用配置）。
        session: 认证服务租户库会话。
        captcha: 验证码基座。
        limiter: 限流基座。
        client: 服务间调用客户端。
        state_store: 流程状态存储（重置 token）。
        notifier: 通知基座（占位发送）。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器（`session.revoked` 广播占位）。

    Returns:
        PasswordResetService: 找回密码服务实例。
    """
    uow = DbUnitOfWork(session)
    return PasswordResetService(
        org_client=OrgCredentialClient(client),
        captcha=captcha,
        rate_limiter=limiter,
        state_store=state_store,
        notifier=notifier,
        session_service=SessionService(
            session=session,
            uow=uow,
            security=security,
            store=store,
            publisher=publisher,
        ),
        settings=request.app.state.settings.password_reset,
    )


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    req: PasswordForgotRequest,
    captcha: CaptchaDep,
    limiter: LimiterDep,
    client: ClientDep,
    state_store: StateStoreDep,
    notifier: NotifierDep,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
) -> ApiResponse[PasswordForgotResult]:
    """发起找回：验证码 / 限流 / 重置目标解析 → 生成令牌并占位发送（恒 `{sent: true}`）。

    Args:
        request: 请求对象（取应用配置与引擎注册表）。
        req: 发起找回请求（标识 / 验证码 / 租户）。
        captcha: 验证码基座。
        limiter: 限流基座。
        client: 服务间调用客户端。
        state_store: 流程状态存储。
        notifier: 通知基座。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。

    Returns:
        ApiResponse: 统一响应，data 为发起结果（`PasswordForgotResult`）。
    """
    tenant = await resolve_request_tenant(req.tenant_code, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            session=session,
            captcha=captcha,
            limiter=limiter,
            client=client,
            state_store=state_store,
            notifier=notifier,
            security=security,
            store=store,
            publisher=publisher,
        )
        result = await service.request_reset(
            req.identifier,
            req.captcha,
            tenant_code=tenant.code,
            ip=current_client_ip.get(),
        )
    return ApiResponse.ok(result)


@router.post("/reset-password")
async def reset_password(
    request: Request,
    req: PasswordResetRequest,
    captcha: CaptchaDep,
    limiter: LimiterDep,
    client: ClientDep,
    state_store: StateStoreDep,
    notifier: NotifierDep,
    security: SecurityDep,
    store: StoreDep,
    publisher: PublisherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
) -> ApiResponse[PasswordResetResult]:
    """提交重置：一次性消费令牌 → 改密（强制过策略）→ 该账号全部会话失效。

    Args:
        request: 请求对象（取应用配置与引擎注册表）。
        req: 提交重置请求（令牌 / 新口令 / 租户）。
        captcha: 验证码基座（未使用，保持服务构造一致）。
        limiter: 限流基座（未使用）。
        client: 服务间调用客户端。
        state_store: 流程状态存储（一次性消费令牌）。
        notifier: 通知基座（未使用）。
        security: 会话安全原语。
        store: 会话标记存储。
        publisher: 实时推送器。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。

    Returns:
        ApiResponse: 统一响应，data 为重置结果（`PasswordResetResult`）。
    """
    tenant = await resolve_request_tenant(req.tenant_code, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            session=session,
            captcha=captcha,
            limiter=limiter,
            client=client,
            state_store=state_store,
            notifier=notifier,
            security=security,
            store=store,
            publisher=publisher,
        )
        result = await service.reset_password(req.token, req.new_password, tenant_code=tenant.code)
    return ApiResponse.ok(result)
