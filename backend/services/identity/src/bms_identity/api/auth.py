"""认证与身份服务端点：网关认证内部端点 + 本地登录 / 刷新 / 登出。

- `POST /api/v1/auth/introspect`：网关 forward-auth 内部端点（见下方说明）。
- `POST /api/v1/auth/login` / `refresh` / `logout`：本地账号密码登录链路（公开路径，经网关转发）；
  access 在响应体、refresh 走 httpOnly cookie（`bms_refresh_token`）。
"""

from typing import Annotated

from fastapi import Depends, Header, Request, Response

from bms_core.api.base import BaseRouter
from bms_core.api.deps import (
    get_captcha,
    get_rate_limiter,
    get_service_client,
    get_service_token_issuer,
    get_session_security,
    get_session_store,
    get_tenant,
    get_tenant_source,
    get_token_verifier,
    get_user_token_issuer,
)
from bms_core.captcha.base import BaseCaptcha
from bms_core.core.context import current_client_ip
from bms_core.core.exceptions import AuthError, ConfigError, ServiceUnavailableError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.edge.headers import TENANT_ID_HEADER, USER_SCOPES_HEADER, USER_SUBJECT_HEADER
from bms_core.oauth.token import TOKEN_AUDIENCE_API, BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.oauth.user_token import BaseUserTokenIssuer
from bms_core.oauth.verify import BaseTokenVerifier
from bms_core.ratelimit.base import BaseRateLimiter
from bms_core.schemas.common import ApiResponse
from bms_core.security.base import BaseSessionSecurity
from bms_core.servicecall.base import BaseServiceClient
from bms_core.session.base import BaseSessionStore
from bms_identity.schemas.auth import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    LoginRequest,
    LoginResult,
    RefreshResult,
)
from bms_identity.services.auth import LoginService
from bms_identity.services.org_client import OrgCredentialClient

router = BaseRouter(key="auth", prefix="/auth", tags=["auth"], default_responses=False)

_BEARER_PREFIX = "bearer "
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Bearer error="invalid_token"'}


@router.get("/introspect")
@router.post("/introspect")
async def introspect(
    request: Request,
    verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
    issuer: Annotated[BaseServiceTokenIssuer, Depends(get_service_token_issuer)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    forwarded_uri: Annotated[str | None, Header(alias="X-Forwarded-Uri")] = None,
) -> Response:
    """网关认证子请求：公开路径放行；受保护路径校验用户 JWT 并换发网关服务 JWT。

    Args:
        request: 请求对象（取应用配置）。
        verifier: 统一校验器（按 `aud=api` 校验用户 JWT）。
        issuer: 服务 JWT 签发者（换发网关服务 JWT）。
        authorization: 客户端 `Authorization` 头（网关经 `request_headers` 转发）。
        forwarded_uri: 原始请求 URI（网关 `forward-auth` 添加的 `X-Forwarded-Uri`）。

    Returns:
        Response: 200（公开路径 / 校验通过，含身份头与网关服务 JWT）或 401 / 503。
    """
    settings = request.app.state.settings
    path = (forwarded_uri or str(request.url.path)).split("?", 1)[0]
    if _is_public(path, settings.gateway.public_paths):
        return Response(status_code=200)

    token = _bearer_token(authorization)
    if token is None:
        return Response(status_code=401, headers=_UNAUTHORIZED_HEADERS)

    try:
        verified = await verifier.verify(token, audience=TOKEN_AUDIENCE_API)
    except AuthError:
        return Response(status_code=401, headers=_UNAUTHORIZED_HEADERS)
    except ServiceUnavailableError:
        return Response(status_code=503)

    spec = ServiceTokenSpec(
        service=settings.gateway.service_identity,
        scopes=("gateway",),
        tenant=verified.tenant,
        ttl=settings.gateway.token_ttl_seconds,
    )
    try:
        issued = await issuer.issue(spec)
    except ConfigError:
        return Response(status_code=503)

    headers = {USER_SUBJECT_HEADER: verified.subject, "Authorization": f"Bearer {issued.access_token}"}
    if verified.tenant:
        headers[TENANT_ID_HEADER] = verified.tenant
    if verified.scopes:
        headers[USER_SCOPES_HEADER] = ",".join(verified.scopes)
    return Response(status_code=200, headers=headers)


def _bearer_token(authorization: str | None) -> str | None:
    """取 Bearer 令牌（大小写不敏感）。

    Args:
        authorization: `Authorization` 头原始值。

    Returns:
        str | None: 令牌紧凑串；缺失 / 非 Bearer 为 None。
    """
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    return authorization[len(_BEARER_PREFIX) :].strip() or None


def _is_public(path: str, public_paths: list[str]) -> bool:
    """判定是否公开路径（前缀匹配）。

    Args:
        path: 原始请求路径（已去查询串）。
        public_paths: 公开路径清单（外部路径形态）。

    Returns:
        bool: 命中任一公开路径前缀为 True。
    """
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in public_paths)


IssuerDep = Annotated[BaseUserTokenIssuer, Depends(get_user_token_issuer)]
SecurityDep = Annotated[BaseSessionSecurity, Depends(get_session_security)]
StoreDep = Annotated[BaseSessionStore, Depends(get_session_store)]
CaptchaDep = Annotated[BaseCaptcha, Depends(get_captcha)]
LimiterDep = Annotated[BaseRateLimiter, Depends(get_rate_limiter)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
TenantSourceDep = Annotated[TenantLookup, Depends(get_tenant_source)]


async def _resolve_login_tenant(
    body_tenant: str | None,
    context_tenant: TenantContext | None,
    source: TenantLookup,
) -> TenantContext:
    """解析登录生效租户：请求上下文优先，无则 body 指定，再校验存在。

    Args:
        body_tenant: 请求体携带的租户编码（可选；不一致时以之为准）。
        context_tenant: 请求上下文（子域名 / `X-Tenant-ID`）租户。
        source: 租户源（按编码校验存在）。

    Returns:
        TenantContext: 生效租户上下文。

    Raises:
        TenantNotFoundError: 无任何租户来源（404）。
    """
    if body_tenant:
        return await source.by_code(body_tenant)
    if context_tenant is not None:
        return context_tenant
    raise TenantNotFoundError("未提供租户标识")


def _build_service(
    *,
    request: Request,
    session: DbSession,
    issuer: BaseUserTokenIssuer,
    security: BaseSessionSecurity,
    store: BaseSessionStore,
    captcha: BaseCaptcha,
    limiter: BaseRateLimiter,
    client: BaseServiceClient,
) -> LoginService:
    """构造登录服务（请求级会话 + 各能力域 + 配置）。

    Args:
        request: 请求对象（取应用配置）。
        session: 认证服务租户库会话。
        issuer: 用户双 token 签发者。
        security: 会话安全原语。
        store: 会话标记存储。
        captcha: 验证码基座。
        limiter: 限流基座。
        client: 服务间调用客户端。

    Returns:
        LoginService: 登录服务实例。
    """
    return LoginService(
        session=session,
        uow=DbUnitOfWork(session),
        user_token_issuer=issuer,
        session_security=security,
        session_store=store,
        captcha=captcha,
        rate_limiter=limiter,
        org_client=OrgCredentialClient(client),
        login_settings=request.app.state.settings.login,
    )


def _set_refresh_cookie(response: Response, request: Request, token: str, max_age: int) -> None:
    """下发 refresh cookie（HttpOnly + Secure（配置）+ SameSite=Lax + 认证路径）。

    Args:
        response: 响应对象。
        request: 请求对象（取 cookie 安全开关）。
        token: refresh token 紧凑串。
        max_age: 有效期（秒）。
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=bool(request.app.state.settings.login.cookie_secure),
        samesite="lax",
    )


@router.post("/login")
async def login(
    request: Request,
    req: LoginRequest,
    response: Response,
    issuer: IssuerDep,
    security: SecurityDep,
    store: StoreDep,
    captcha: CaptchaDep,
    limiter: LimiterDep,
    client: ClientDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
) -> ApiResponse[LoginResult]:
    """本地账号密码登录：验证码 / 限流 / org 凭据校验 → 签发双 token 并建会话。

    Args:
        request: 请求对象。
        req: 登录请求。
        response: 响应对象（下发 refresh cookie）。
        issuer: 用户双 token 签发者。
        security: 会话安全原语。
        store: 会话标记存储。
        captcha: 验证码基座。
        limiter: 限流基座。
        client: 服务间调用客户端。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。

    Returns:
        ApiResponse: 统一响应，data 为登录结果（`LoginResult`）。
    """
    tenant = await _resolve_login_tenant(req.tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            session=session,
            issuer=issuer,
            security=security,
            store=store,
            captcha=captcha,
            limiter=limiter,
            client=client,
        )
        outcome = await service.login(
            req,
            tenant=tenant.tenant_code,
            ip=current_client_ip.get(),
            user_agent=request.headers.get("user-agent"),
        )
    _set_refresh_cookie(response, request, outcome.refresh_token, outcome.refresh_expires_in)
    return ApiResponse.ok(outcome.result)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    issuer: IssuerDep,
    security: SecurityDep,
    store: StoreDep,
    captcha: CaptchaDep,
    limiter: LimiterDep,
    client: ClientDep,
    tenant_ctx: TenantDep,
) -> ApiResponse[RefreshResult]:
    """静默刷新：校验 refresh 并轮换签发新双 token（同会话 id）。

    Args:
        request: 请求对象（读 refresh cookie）。
        response: 响应对象（重设 refresh cookie）。
        issuer: 用户双 token 签发者。
        security: 会话安全原语。
        store: 会话标记存储。
        captcha: 验证码基座（未使用，保持服务构造一致）。
        limiter: 限流基座（未使用）。
        client: 服务间调用客户端（未使用）。
        tenant_ctx: 请求上下文租户。

    Returns:
        ApiResponse: 统一响应，data 为刷新结果（`RefreshResult`）。

    Raises:
        AuthError: 缺少 refresh cookie / 租户上下文（20001/401）。
    """
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not token:
        raise AuthError("缺少刷新令牌")
    if tenant_ctx is None:
        raise AuthError("缺少租户标识")
    registry: EngineRegistry = request.app.state.engine_registry
    factory = request.app.state.session_factory
    async with session_scope(registry, db_key=tenant_ctx.db_key, factory=factory) as session:
        service = _build_service(
            request=request,
            session=session,
            issuer=issuer,
            security=security,
            store=store,
            captcha=captcha,
            limiter=limiter,
            client=client,
        )
        outcome = await service.refresh(
            token,
            tenant=tenant_ctx.tenant_code,
            ip=current_client_ip.get(),
            user_agent=request.headers.get("user-agent"),
        )
    _set_refresh_cookie(response, request, outcome.refresh_token, outcome.refresh_expires_in)
    return ApiResponse.ok(outcome.result)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    issuer: IssuerDep,
    security: SecurityDep,
    store: StoreDep,
    captcha: CaptchaDep,
    limiter: LimiterDep,
    client: ClientDep,
    tenant_ctx: TenantDep,
) -> ApiResponse[None]:
    """登出（幂等）：refresh 入黑名单 + 会话撤销 + 删标记；清 cookie。

    Args:
        request: 请求对象（读 refresh cookie）。
        response: 响应对象（清 refresh cookie）。
        issuer: 用户双 token 签发者。
        security: 会话安全原语。
        store: 会话标记存储。
        captcha: 验证码基座（未使用，保持服务构造一致）。
        limiter: 限流基座（未使用）。
        client: 服务间调用客户端（未使用）。
        tenant_ctx: 请求上下文租户。

    Returns:
        ApiResponse: 统一响应（data 为 null）。
    """
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    if token and tenant_ctx is not None:
        registry: EngineRegistry = request.app.state.engine_registry
        factory = request.app.state.session_factory
        async with session_scope(registry, db_key=tenant_ctx.db_key, factory=factory) as session:
            service = _build_service(
                request=request,
                session=session,
                issuer=issuer,
                security=security,
                store=store,
                captcha=captcha,
                limiter=limiter,
                client=client,
            )
            await service.logout(token, tenant=tenant_ctx.tenant_code)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return ApiResponse.ok(None)
