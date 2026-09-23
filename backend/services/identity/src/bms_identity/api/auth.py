"""网关认证内部端点：`POST /api/v1/auth/introspect`（forward-auth 校验用户 JWT 并换发网关服务 JWT）。

- **内部端点**：仅供 APISIX 网关经内网直连调用（不经网关业务路由）；豁免租户解析与边缘旁路拒绝。
- **公开路径**：按 `X-Forwarded-Uri` + `[gateway].public_paths`（登录 / 刷新 / 验证码）判定，免认证返回 200。
- **受保护路径**：用 `UnifiedTokenVerifier` 按 `aud=api` 全校验用户 JWT（签名 / `exp` / `iss` / `aud`），
  通过后返回契约身份头（`X-User-Subject` / `X-Tenant-Id` / `X-User-Scopes`），并**换发短时网关服务 JWT**
  （`aud=service`，`sub=[gateway].service_identity`）随 `Authorization` 回传——网关据此注入上游、后端只信
  有效服务 JWT。
- **失败语义**：缺失 / 无效用户 JWT → 401（`WWW-Authenticate`）；IdP JWKS 不可达 → 503；签发不可用 → 503。
"""

from typing import Annotated

from fastapi import Depends, Header, Request, Response

from bms_core.api.base import BaseRouter
from bms_core.api.deps import get_service_token_issuer, get_token_verifier
from bms_core.core.exceptions import AuthError, ConfigError, ServiceUnavailableError
from bms_core.edge.headers import TENANT_ID_HEADER, USER_SCOPES_HEADER, USER_SUBJECT_HEADER
from bms_core.oauth.token import TOKEN_AUDIENCE_API, BaseServiceTokenIssuer, ServiceTokenSpec
from bms_core.oauth.verify import BaseTokenVerifier

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
