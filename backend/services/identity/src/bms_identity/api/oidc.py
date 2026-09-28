"""认证与身份服务端点：OIDC Provider（BMS 兼作 IdP）五端点。

- `GET /.well-known/openid-configuration` / `GET /jwks`：公开，租户经标准解析链确定。
- `GET /authorize`：公开；`require_auth`（未登录 → `302 {login_url}?return_to=` 或 401）→ 签发授权码回跳。
- `POST /token`：公开；客户端认证（basic / post）→ 换码（标准 OAuth2 JSON）。
- `GET/POST /userinfo`：公开；Bearer access token → 标准 userinfo JSON。

错误形态：OIDC 端点用标准 OAuth2 `{error, error_description}`（`OidcError` 端点边界转换），
不进平台统一响应体。
"""

from __future__ import annotations

import base64
import time
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.datastructures import FormData

from bms_core.api.base import AuthContext, BaseRouter, require_auth
from bms_core.api.deps import (
    get_idp_state_store,
    get_oidc_provider,
    get_password_hasher,
    get_service_client,
    get_session_store,
    get_tenant,
    get_tenant_source,
    get_token_verifier,
)
from bms_core.core.exceptions import AuthError, OidcAccessDeniedError, OidcError, OidcInvalidRequestError
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import DbSession, session_scope
from bms_core.db.tenant import TenantContext, TenantLookup, TenantNotFoundError
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.oauth.oidc_provider import BaseOidcProvider
from bms_core.oauth.verify import BaseTokenVerifier
from bms_core.security.base import BasePasswordHasher
from bms_core.servicecall.base import BaseServiceClient
from bms_core.session.base import BaseSessionStore
from bms_identity.schemas.oidc import TokenResponse, UserInfoResponse
from bms_identity.services.oidc_provider import OidcProviderService
from bms_identity.services.org_client import OrgCredentialClient

router = BaseRouter(key="oidc", prefix="/oidc", tags=["oidc"], default_responses=False)

_GOOD_HTML = {"Cache-Control": "no-store"}

ProviderDep = Annotated[BaseOidcProvider, Depends(get_oidc_provider)]
StateStoreDep = Annotated[BaseIdpStateStore, Depends(get_idp_state_store)]
ClientDep = Annotated[BaseServiceClient, Depends(get_service_client)]
HasherDep = Annotated[BasePasswordHasher, Depends(get_password_hasher)]
TenantDep = Annotated[TenantContext | None, Depends(get_tenant)]
TenantSourceDep = Annotated[TenantLookup, Depends(get_tenant_source)]


async def _optional_auth(
    request: Request,
    verifier: Annotated[BaseTokenVerifier, Depends(get_token_verifier)],
    store: Annotated[BaseSessionStore, Depends(get_session_store)],
) -> AuthContext | None:
    """可选登录态（未登录返回 None，不抛错；供 `/authorize` 决定跳登录页）。

    Args:
        request: 请求对象。
        verifier: 统一校验器。
        store: 会话标记存储。

    Returns:
        AuthContext | None: 登录态；未登录为 None。
    """
    try:
        return await require_auth(request, verifier, store)
    except AuthError:
        return None


OptionalAuthDep = Annotated[AuthContext | None, Depends(_optional_auth)]


async def _resolve(tenant: str | None, context: TenantContext | None, source: TenantLookup) -> TenantContext:
    """解析 OIDC 端点生效租户（异步版）。

    Args:
        tenant: 查询参数租户编码（可选）。
        context: 请求上下文租户。
        source: 租户源。

    Returns:
        TenantContext: 生效租户。

    Raises:
        TenantNotFoundError: 无任何租户来源（404）。
    """
    if tenant:
        if context is not None and context.code == tenant:
            return context
        return await source.by_code(tenant)
    if context is not None:
        return context
    raise TenantNotFoundError("未提供租户标识")


def _build_service(
    *,
    request: Request,
    session: DbSession,
    provider: BaseOidcProvider,
    state_store: BaseIdpStateStore,
    client: BaseServiceClient,
    hasher: BasePasswordHasher,
) -> OidcProviderService:
    """构造 OIDC Provider 服务（请求级会话 + 能力域 + 配置）。

    Args:
        request: 请求对象（取配置）。
        session: 租户库会话。
        provider: OIDC Provider 能力域。
        state_store: 流程状态存储。
        client: 服务间调用客户端。
        hasher: 口令哈希实现。

    Returns:
        OidcProviderService: 编排服务。
    """
    return OidcProviderService(
        session=session,
        provider=provider,
        state_store=state_store,
        org_client=OrgCredentialClient(client),
        password_hasher=hasher,
        settings=request.app.state.settings.oidc_provider,
    )


@router.get("/.well-known/openid-configuration")
async def openid_configuration(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    client: ClientDep,
    hasher: HasherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> JSONResponse:
    """OIDC Discovery 文档（标准 JSON，无统一响应包体）。

    Args:
        request: 请求对象。
        provider: OIDC Provider。
        state_store: 流程状态存储（保持服务构造一致）。
        client: 服务间调用客户端（保持服务构造一致）。
        hasher: 口令哈希（保持服务构造一致）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        tenant: 租户编码（可选）。

    Returns:
        JSONResponse: Discovery 文档。
    """
    context = await _resolve(tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    async with session_scope(registry, db_key=context.db_key, factory=request.app.state.session_factory) as session:
        service = _build_service(
            request=request,
            session=session,
            provider=provider,
            state_store=state_store,
            client=client,
            hasher=hasher,
        )
        document = await service.discovery(context.code)
    return JSONResponse(content=document, headers=_GOOD_HTML)


@router.get("/jwks")
async def jwks(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    client: ClientDep,
    hasher: HasherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> JSONResponse:
    """IdP 公开 JWKS（标准 JSON，无统一响应包体）。

    Args:
        request: 请求对象。
        provider: OIDC Provider。
        state_store: 流程状态存储（保持服务构造一致）。
        client: 服务间调用客户端（保持服务构造一致）。
        hasher: 口令哈希（保持服务构造一致）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        tenant: 租户编码（可选）。

    Returns:
        JSONResponse: JWKS 文档。
    """
    await _resolve(tenant, tenant_ctx, tenant_source)
    return JSONResponse(content=dict(provider.jwks()), headers=_GOOD_HTML)


@router.get("/authorize")
async def authorize(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    client: ClientDep,
    hasher: HasherDep,
    auth: OptionalAuthDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    response_type: Annotated[str | None, Query()] = None,
    client_id: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
    scope: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    nonce: Annotated[str | None, Query()] = None,
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> Response:
    """授权端点：校验客户端并签发一次性授权码，`302` 回跳 `redirect_uri`。

    Args:
        request: 请求对象。
        provider: OIDC Provider。
        state_store: 流程状态存储（授权码一次性）。
        client: 服务间调用客户端（保持服务构造一致）。
        hasher: 口令哈希（保持服务构造一致）。
        auth: 可选登录态。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        response_type: 响应类型（须为 `code`）。
        client_id: 客户端标识。
        redirect_uri: 回跳地址。
        scope: 申请 scope。
        state: 透传状态。
        nonce: 透传 nonce。
        code_challenge: PKCE 挑战。
        code_challenge_method: PKCE 方法。
        tenant: 租户编码（可选）。

    Returns:
        Response: `302` 回跳地址。

    Raises:
        OidcAccessDeniedError: 未登录且未配登录页（80106/401）。
        OidcInvalidRequestError: 客户端未知 / `redirect_uri` 不可信（80101/400）。
    """
    try:
        if auth is None:
            return _login_redirect(request)
        if tenant and auth.tenant_code and tenant != auth.tenant_code:
            raise OidcInvalidRequestError("租户与登录态不一致")
        context = await _resolve(auth.tenant_code or tenant, tenant_ctx, tenant_source)
        registry: EngineRegistry = request.app.state.engine_registry
        async with session_scope(registry, db_key=context.db_key, factory=request.app.state.session_factory) as session:
            service = _build_service(
                request=request,
                session=session,
                provider=provider,
                state_store=state_store,
                client=client,
                hasher=hasher,
            )
            result = await service.authorize(
                tenant=context.code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                response_type=response_type,
                scope=scope,
                state=state,
                nonce=nonce,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                subject=str(auth.user_id) if auth.user_id is not None else auth.subject,
                auth_time=int(time.time()),
            )
    except OidcError as exc:
        return _oauth_error(exc)
    return RedirectResponse(result.redirect_url, status_code=302)


@router.post("/token")
async def token(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    client: ClientDep,
    hasher: HasherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> Response:
    """令牌端点：客户端认证 + 授权码换 ID Token / access token（标准 OAuth2 JSON）。

    Args:
        request: 请求对象。
        provider: OIDC Provider。
        state_store: 流程状态存储（授权码一次性消费）。
        client: 服务间调用客户端（org 用户概要）。
        hasher: 口令哈希（客户端密钥比对）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        tenant: 租户编码（可选）。

    Returns:
        Response: 标准令牌 JSON 或标准错误 JSON。
    """
    form = await request.form()
    client_id, client_secret = _client_credentials(request, form)
    context = await _resolve(tenant, tenant_ctx, tenant_source)
    registry: EngineRegistry = request.app.state.engine_registry
    try:
        async with session_scope(registry, db_key=context.db_key, factory=request.app.state.session_factory) as session:
            service = _build_service(
                request=request,
                session=session,
                provider=provider,
                state_store=state_store,
                client=client,
                hasher=hasher,
            )
            result = await service.token(
                tenant=context.code,
                client_id=client_id,
                client_secret=client_secret,
                grant_type=_form_str(form, "grant_type"),
                code=_form_str(form, "code"),
                redirect_uri=_form_str(form, "redirect_uri"),
                code_verifier=_form_str(form, "code_verifier"),
            )
    except OidcError as exc:
        return _oauth_error(exc)
    return JSONResponse(
        content=TokenResponse(
            access_token=result.access_token,
            token_type=result.token_type,
            expires_in=result.expires_in,
            id_token=result.id_token,
            scope=result.scope,
        ).model_dump(mode="json"),
        headers=_GOOD_HTML,
    )


@router.get("/userinfo")
@router.post("/userinfo")
async def userinfo(
    request: Request,
    provider: ProviderDep,
    state_store: StateStoreDep,
    client: ClientDep,
    hasher: HasherDep,
    tenant_ctx: TenantDep,
    tenant_source: TenantSourceDep,
    tenant: Annotated[str | None, Query(description="租户编码（上下文缺省时的回落）")] = None,
) -> Response:
    """用户信息端点：Bearer access token → 标准 userinfo JSON。

    Args:
        request: 请求对象。
        provider: OIDC Provider。
        state_store: 流程状态存储（保持服务构造一致）。
        client: 服务间调用客户端（org 用户概要）。
        hasher: 口令哈希（保持服务构造一致）。
        tenant_ctx: 请求上下文租户。
        tenant_source: 租户源。
        tenant: 租户编码（可选）。

    Returns:
        Response: 标准 userinfo JSON 或 401。
    """
    context = await _resolve(tenant, tenant_ctx, tenant_source)
    token_value = _bearer(request.headers.get("authorization"))
    if not token_value:
        return _unauthorized()
    registry: EngineRegistry = request.app.state.engine_registry
    try:
        async with session_scope(registry, db_key=context.db_key, factory=request.app.state.session_factory) as session:
            service = _build_service(
                request=request,
                session=session,
                provider=provider,
                state_store=state_store,
                client=client,
                hasher=hasher,
            )
            result = await service.userinfo(tenant=context.code, access_token=token_value)
    except AuthError:
        return _unauthorized()
    return JSONResponse(
        content=UserInfoResponse(
            sub=result.subject,
            preferred_username=result.preferred_username,
            name=result.name,
        ).model_dump(mode="json"),
        headers=_GOOD_HTML,
    )


def _login_redirect(request: Request) -> Response:
    """未登录：配登录页则 `302`（附 `return_to`），否则 401。

    Args:
        request: 请求对象。

    Returns:
        Response: `302` 跳转或 401。

    Raises:
        OidcAccessDeniedError: 未配置登录页（80106/401）。
    """
    login_url = request.app.state.settings.oidc_provider.login_url
    if not login_url:
        raise OidcAccessDeniedError("未登录")
    return_to = str(request.url)
    separator = "&" if "?" in login_url else "?"
    return RedirectResponse(f"{login_url}{separator}{urlencode({'return_to': return_to})}", status_code=302)


def _oauth_error(exc: OidcError) -> JSONResponse:
    """OidcError → 标准 OAuth2 错误 JSON。

    Args:
        exc: OIDC 异常。

    Returns:
        JSONResponse: 标准错误响应。
    """
    body = {"error": exc.error, "error_description": exc.message or exc.error}
    headers = dict(_GOOD_HTML)
    if exc.error == "invalid_client":
        headers["WWW-Authenticate"] = 'Basic realm="bms-oidc"'
    return JSONResponse(content=body, status_code=exc.http_status, headers=headers)


def _unauthorized() -> JSONResponse:
    """401 标准响应（`WWW-Authenticate: Bearer`）。

    Returns:
        JSONResponse: 401 响应。
    """
    return JSONResponse(
        content={"error": "invalid_token", "error_description": "invalid_token"},
        status_code=401,
        headers={**_GOOD_HTML, "WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


def _client_credentials(request: Request, form: FormData) -> tuple[str | None, str | None]:
    """解析客户端认证（Basic 头优先，其次表单）。

    Args:
        request: 请求对象。
        form: 表单数据。

    Returns:
        tuple[str | None, str | None]: (client_id, client_secret)。
    """
    authorization = request.headers.get("authorization") or ""
    if authorization.lower().startswith("basic "):
        decoded = _decode_basic(authorization[6:])
        if decoded is not None:
            return decoded
    return _form_str(form, "client_id"), _form_str(form, "client_secret")


def _decode_basic(encoded: str) -> tuple[str, str] | None:
    """解析 Basic 认证（`client_id:client_secret`）。

    Args:
        encoded: Base64 编码串。

    Returns:
        tuple[str, str] | None: 解析结果；非法为 None。
    """
    try:
        raw = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except ValueError, UnicodeDecodeError:
        return None
    if ":" not in raw:
        return None
    client_id, _, secret = raw.partition(":")
    return client_id, secret


def _bearer(authorization: str | None) -> str | None:
    """取 Bearer 令牌。

    Args:
        authorization: `Authorization` 头。

    Returns:
        str | None: 令牌串；缺失 / 非 Bearer 为 None。
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization[7:].strip() or None


def _form_str(form: FormData, key: str) -> str | None:
    """读表单字符串字段（缺失 / 非字符串返回 None）。

    Args:
        form: 表单数据。
        key: 字段名。

    Returns:
        str | None: 字段值。
    """
    raw = form.get(key)
    return raw if isinstance(raw, str) and raw != "" else None
