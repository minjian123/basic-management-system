"""认证与身份服务 services 层：OIDC Provider 编排（Discovery / 授权 / 换码 / 用户信息）。

- Discovery / jwks：按租户派生 issuer 与端点，纯读。
- authorize：校验客户端 / `redirect_uri` / scope / PKCE → 生成一次性授权码（`idp_state_store`
  `oidccode` 命名空间）→ 返回回跳 URL（校验失败按 OAuth2 语义带 `error` 回跳；不可信 `redirect_uri`
  一律抛 `OidcInvalidRequestError`，不回跳）。
- token：客户端认证（basic / post）→ 一次性消费授权码 → 校验归属 / `redirect_uri` / PKCE →
  签发 ID Token（`aud=client_id`）与 access token（`aud=userinfo`）。
- userinfo：校验 access token → 经 org 内部接口取用户概要 → 标准声明。

错误语义：校验类失败抛 `OidcError` 子段（端点边界转标准错误 JSON / 回跳）；org 不可达抛
`ServiceUnavailableError`（10007/503，fail-closed）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, cast
from urllib.parse import urlencode

from bms_core.core.base import BaseObject
from bms_core.core.config import OidcProviderSettings
from bms_core.core.exceptions import (
    AuthError,
    OidcInvalidClientError,
    OidcInvalidGrantError,
    OidcInvalidRequestError,
    OidcUnsupportedGrantError,
)
from bms_core.core.objects import BaseAuthorizeUrlResultContract, BaseTokenContract, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.oauth.oidc_provider import (
    OIDC_CODE_NAMESPACE,
    OIDC_GRANT_AUTHORIZATION_CODE,
    OIDC_RESPONSE_TYPE_CODE,
    OIDC_SCOPE_OPENID,
    AccessTokenSpec,
    BaseOidcProvider,
    IdTokenSpec,
    build_discovery_document,
)
from bms_core.security.base import BasePasswordHasher
from bms_identity.models.client import SysClient
from bms_identity.repositories.client import SysClientRepository
from bms_identity.services.org_client import OrgCredentialClient

__all__ = [
    "AuthorizeResult",
    "OidcCode",
    "OidcProviderService",
    "TokenResult",
    "UserInfoResult",
]

_PKCE_METHOD = "S256"


@dataclass(frozen=True)
class OidcCode(BaseValueObject):
    """授权码载荷（一次性；`idp_state_store` `oidccode` 命名空间）。"""

    client_id: str
    redirect_uri: str
    subject: str
    tenant: str
    nonce: str = ""
    code_challenge: str = ""
    code_challenge_method: str = ""
    scope: str = ""
    auth_time: int = 0


@dataclass(frozen=True)
class AuthorizeResult(BaseAuthorizeUrlResultContract):
    """授权端点结果（回跳 URL）。"""

    URL_FIELD: ClassVar[str] = "redirect_url"

    redirect_url: str
    """302 回跳地址（成功带 `code` / `state`，失败带 `error` / `error_description`）。"""

    code: str = ""
    """授权码（成功时非空；测试 / 审计用）。"""


@dataclass(frozen=True)
class TokenResult(BaseTokenContract):
    """令牌端点结果（标准 OAuth2）。"""

    access_token: str
    id_token: str
    expires_in: int
    scope: str = ""
    token_type: str = "Bearer"


@dataclass(frozen=True)
class UserInfoResult(BaseValueObject):
    """userinfo 结果（标准字段；本期不含 email）。

    主体字段统一为 `subject`（09_03 批次 ⑤ 字段名统一；协议输出键 `sub` 在 `UserInfoResponse` schema 层，不受影响）。
    """

    subject: str
    preferred_username: str = ""
    name: str = ""


class OidcProviderService(BaseObject):
    """OIDC Provider 编排服务（每请求装配：会话 / 状态存储 / Provider / org 客户端 / 哈希器）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        provider: BaseOidcProvider,
        state_store: BaseIdpStateStore,
        org_client: OrgCredentialClient,
        password_hasher: BasePasswordHasher,
        settings: OidcProviderSettings,
    ) -> None:
        """初始化。

        Args:
            session: identity 服务租户库会话（读取客户端）。
            provider: OIDC Provider 能力域实例。
            state_store: 流程状态存储（授权码一次性）。
            org_client: org 内部接口客户端（用户概要）。
            password_hasher: 口令哈希实现（客户端密钥校验）。
            settings: `[oidc_provider]` 配置。
        """
        self._repo = SysClientRepository(session)
        self._provider = provider
        self._state = state_store
        self._org = org_client
        self._hasher = password_hasher
        self._settings = settings

    def issuer_for(self, tenant: str) -> str:
        """按租户派生 issuer（配置可含 `{tenant}` 占位）。

        Args:
            tenant: 租户编码。

        Returns:
            str: issuer（无占位时原样返回）。
        """
        template = self._settings.issuer
        try:
            return template.format(tenant=tenant)
        except KeyError, IndexError, ValueError:
            return template

    async def discovery(self, tenant: str) -> dict[str, object]:
        """构造 Discovery 文档（issuer 与端点按租户派生）。

        Args:
            tenant: 租户编码。

        Returns:
            dict[str, object]: OIDC Discovery 文档。
        """
        issuer = self.issuer_for(tenant)
        return build_discovery_document(
            issuer=issuer,
            authorization_endpoint=f"{issuer}/authorize",
            token_endpoint=f"{issuer}/token",
            userinfo_endpoint=f"{issuer}/userinfo",
            jwks_uri=f"{issuer}/jwks",
        )

    async def authorize(
        self,
        *,
        tenant: str,
        client_id: str | None,
        redirect_uri: str | None,
        response_type: str | None,
        scope: str | None,
        state: str | None,
        nonce: str | None,
        code_challenge: str | None,
        code_challenge_method: str | None,
        subject: str,
        auth_time: int,
    ) -> AuthorizeResult:
        """授权端点：校验并签发授权码，返回回跳 URL。

        Args:
            tenant: 生效租户编码。
            client_id: 客户端标识（请求参数）。
            redirect_uri: 回跳地址（请求参数）。
            response_type: 响应类型（须为 `code`）。
            scope: 申请 scope（空格分隔）。
            state: 透传状态（可选）。
            nonce: 透传 nonce（可选）。
            code_challenge: PKCE 挑战（可选 / 公共客户端必填）。
            code_challenge_method: PKCE 方法（须为 S256）。
            subject: 已登录用户主体（BMS 用户 id 字符串）。
            auth_time: 用户认证时间（Unix 秒）。

        Returns:
            AuthorizeResult: 回跳 URL。

        Raises:
            OidcInvalidRequestError: 客户端未知 / `redirect_uri` 不可信 / 缺必需参数（不回跳）。
        """
        if not client_id or not redirect_uri or not response_type:
            raise OidcInvalidRequestError("缺少 client_id / redirect_uri / response_type")
        client = await self._load_client(client_id)
        redirect_uri = self._validate_redirect(client, redirect_uri)
        failure = self._authorize_failure(client, response_type, scope, code_challenge, code_challenge_method)
        if failure is not None:
            return AuthorizeResult(redirect_url=redirect_error(redirect_uri, failure, state), code="")
        requested_scope = clean_scope(scope)
        code = secrets.token_urlsafe(32)
        payload = OidcCode(
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            subject=subject,
            tenant=tenant,
            nonce=nonce or "",
            code_challenge=code_challenge or "",
            code_challenge_method=code_challenge_method or "",
            scope=requested_scope,
            auth_time=auth_time,
        )
        await self._state.save(
            code,
            _code_payload(payload),
            tenant=tenant,
            ttl=self._settings.authorization_code_ttl_seconds,
            namespace=OIDC_CODE_NAMESPACE,
        )
        query = urlencode({"code": code, **({"state": state} if state else {})})
        return AuthorizeResult(redirect_url=with_query(redirect_uri, query), code=code)

    async def token(
        self,
        *,
        tenant: str,
        client_id: str | None,
        client_secret: str | None,
        grant_type: str | None,
        code: str | None,
        redirect_uri: str | None,
        code_verifier: str | None,
    ) -> TokenResult:
        """令牌端点：换码签发 ID Token 与 access token。

        Args:
            tenant: 生效租户编码。
            client_id: 客户端标识（basic 头解析后或表单传入）。
            client_secret: 客户端密钥（公共客户端为空）。
            grant_type: 授权类型（须为 `authorization_code`）。
            code: 授权码。
            redirect_uri: 与授权时一致的 `redirect_uri`。
            code_verifier: PKCE 校验码（授权时提交挑战则必填）。

        Returns:
            TokenResult: 令牌结果。

        Raises:
            OidcUnsupportedGrantError: `grant_type` 非授权码（80105/400）。
            OidcInvalidClientError: 客户端认证失败（80102/401）。
            OidcInvalidGrantError: 授权码 / `redirect_uri` / PKCE 校验失败（80103/400）。
        """
        if grant_type != OIDC_GRANT_AUTHORIZATION_CODE:
            raise OidcUnsupportedGrantError("仅支持 authorization_code")
        if not client_id or not code or not redirect_uri:
            raise OidcInvalidGrantError("缺少 client_id / code / redirect_uri")
        client = await self._load_client(client_id, invalid_client=True)
        self._authenticate(client, client_secret)
        raw = await self._state.consume(code, tenant=tenant, namespace=OIDC_CODE_NAMESPACE)
        record = code_from_payload(raw)
        if record.client_id != client.client_id or record.redirect_uri != redirect_uri:
            raise OidcInvalidGrantError("授权码与客户端 / 回跳地址不符")
        if record.code_challenge and not verify_pkce(record.code_challenge, code_verifier):
            raise OidcInvalidGrantError("PKCE 校验失败")
        issuer = self.issuer_for(tenant)
        profile = await self._org.user_profile(record.tenant, int(record.subject))
        if not profile.found or profile.user is None or profile.user.status != "enabled":
            raise OidcInvalidGrantError("用户不存在或不可用")
        id_token = await self._provider.issue_id_token(
            IdTokenSpec(
                subject=record.subject,
                client_id=client.client_id,
                issuer=issuer,
                nonce=record.nonce,
                auth_time=record.auth_time,
                preferred_username=profile.user.username,
                name=profile.user.name,
                ttl=self._settings.id_token_ttl_seconds,
            )
        )
        access_token = await self._provider.issue_access_token(
            AccessTokenSpec(
                subject=record.subject,
                tenant=record.tenant,
                client_id=client.client_id,
                issuer=issuer,
                scopes=tuple(record.scope.split()) if record.scope else (),
                ttl=self._settings.access_token_ttl_seconds,
            )
        )
        return TokenResult(
            access_token=access_token,
            id_token=id_token,
            expires_in=self._settings.access_token_ttl_seconds,
            scope=record.scope,
        )

    async def userinfo(self, *, tenant: str, access_token: str) -> UserInfoResult:
        """用户信息端点：校验 access token 并取用户概要。

        Args:
            tenant: 生效租户编码。
            access_token: Bearer access token。

        Returns:
            UserInfoResult: 标准用户信息。

        Raises:
            AuthError: 令牌非法 / 跨租户 / 用户不可用（20001/401）。
            ServiceUnavailableError: org 接口不可达（10007/503）。
        """
        issuer = self.issuer_for(tenant)
        claims = self._provider.verify_access_token(access_token, issuer=issuer)
        if claims.tenant and claims.tenant != tenant:
            raise AuthError("令牌租户与请求租户不符")
        profile = await self._org.user_profile(tenant, int(claims.subject))
        if not profile.found or profile.user is None or profile.user.status != "enabled":
            raise AuthError("用户不存在或不可用")
        return UserInfoResult(
            subject=claims.subject,
            preferred_username=profile.user.username,
            name=profile.user.name,
        )

    async def _load_client(self, client_id: str, *, invalid_client: bool = False) -> SysClient:
        """按标识取启用客户端（不存在 / 停用按语义抛错）。

        Args:
            client_id: 客户端标识。
            invalid_client: True 时抛 `OidcInvalidClientError`，否则抛 `OidcInvalidRequestError`。

        Returns:
            SysClient: 客户端行。

        Raises:
            OidcInvalidClientError: `invalid_client=True` 且未命中 / 停用（80102/401）。
            OidcInvalidRequestError: 未命中 / 停用（80101/400）。
        """
        client = await self._repo.get_by_client_id(client_id)
        if client is None or client.status != "enabled":
            if invalid_client:
                raise OidcInvalidClientError("客户端无效")
            raise OidcInvalidRequestError("客户端无效")
        return client

    def _validate_redirect(self, client: SysClient, redirect_uri: str) -> str:
        """校验 `redirect_uri` 精确命中已注册集合（防开放重定向）。

        Args:
            client: 客户端行。
            redirect_uri: 请求 `redirect_uri`。

        Returns:
            str: 校验通过的 `redirect_uri`。

        Raises:
            OidcInvalidRequestError: 未命中已注册集合（80101/400）。
        """
        registered = load_list(client.redirect_uris)
        if redirect_uri not in registered:
            raise OidcInvalidRequestError("redirect_uri 未注册")
        return redirect_uri

    def _authorize_failure(
        self,
        client: SysClient,
        response_type: str,
        scope: str | None,
        code_challenge: str | None,
        code_challenge_method: str | None,
    ) -> str | None:
        """授权校验（可回跳的失败返回 OAuth2 error 串，成功返回 None）。

        Args:
            client: 客户端行。
            response_type: 响应类型。
            scope: 申请 scope。
            code_challenge: PKCE 挑战。
            code_challenge_method: PKCE 方法。

        Returns:
            str | None: 失败时的 `error` 串；成功为 None。
        """
        if response_type != OIDC_RESPONSE_TYPE_CODE:
            return "unsupported_response_type"
        if OIDC_GRANT_AUTHORIZATION_CODE not in load_list(client.grant_types):
            return "unauthorized_client"
        requested = set(clean_scope(scope).split())
        registered = set(load_list(client.scopes))
        if OIDC_SCOPE_OPENID not in requested or not requested <= registered:
            return "invalid_scope"
        is_public = not client.client_secret_hash
        if code_challenge:
            if code_challenge_method != _PKCE_METHOD:
                return "invalid_request"
        elif is_public:
            return "invalid_request"
        return None

    def _authenticate(self, client: SysClient, client_secret: str | None) -> None:
        """客户端认证（公共客户端不接受密钥；机密客户端常量时间比对）。

        Args:
            client: 客户端行。
            client_secret: 请求密钥（可空）。

        Raises:
            OidcInvalidClientError: 认证失败（80102/401）。
        """
        secret = (client_secret or "").strip()
        if not client.client_secret_hash:
            if secret:
                raise OidcInvalidClientError("公共客户端不接受密钥")
            return
        if not secret or not self._hasher.verify(secret, client.client_secret_hash):
            raise OidcInvalidClientError("客户端密钥错误")


def clean_scope(scope: str | None) -> str:
    """归一化 scope（去重、去空、空格连接）。

    Args:
        scope: 原始 scope 串。

    Returns:
        str: 归一化 scope。
    """
    if not scope:
        return ""
    seen: list[str] = []
    for item in scope.split():
        if item and item not in seen:
            seen.append(item)
    return " ".join(seen)


def redirect_error(redirect_uri: str, error: str, state: str | None) -> str:
    """构造带 OAuth2 错误参数的 302 回跳地址。

    Args:
        redirect_uri: 已校验的回跳地址。
        error: OAuth2 错误串。
        state: 透传状态（可选）。

    Returns:
        str: 回跳地址。
    """
    params: dict[str, str] = {"error": error, "error_description": error}
    if state:
        params["state"] = state
    return with_query(redirect_uri, urlencode(params))


def with_query(target: str, query: str) -> str:
    """拼接查询串（保留既有查询参数）。

    Args:
        target: 目标地址。
        query: 追加查询串。

    Returns:
        str: 拼接后的地址。
    """
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}{query}"


def verify_pkce(challenge: str, verifier: str | None) -> bool:
    """校验 PKCE S256（`challenge == BASE64URL(SHA256(verifier))`）。

    Args:
        challenge: 授权时存储的挑战值。
        verifier: 换码提交的校验码。

    Returns:
        bool: 匹配为 True。
    """
    if not verifier:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


def load_list(raw: str | None) -> list[str]:
    """解析 JSON 数组字段（非法 / 非数组返回空列表）。

    Args:
        raw: 列原文。

    Returns:
        list[str]: 字符串列表。
    """
    try:
        parsed = json.loads(raw or "[]")
    except ValueError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in cast("list[object]", parsed)]


def _code_payload(code: OidcCode) -> dict[str, object]:
    """授权码载荷 → 存储 payload。

    Args:
        code: 授权码载荷。

    Returns:
        dict[str, object]: payload。
    """
    return {
        "client_id": code.client_id,
        "redirect_uri": code.redirect_uri,
        "subject": code.subject,
        "tenant": code.tenant,
        "nonce": code.nonce,
        "code_challenge": code.code_challenge,
        "code_challenge_method": code.code_challenge_method,
        "scope": code.scope,
        "auth_time": code.auth_time,
    }


def code_from_payload(raw: Mapping[str, object] | None) -> OidcCode:
    """存储 payload → 授权码载荷（缺失 / 非法按无效授权码）。

    Args:
        raw: 存储返回值。

    Returns:
        OidcCode: 授权码载荷。

    Raises:
        OidcInvalidGrantError: payload 缺失 / 结构非法（80103/400）。
    """
    if not isinstance(raw, Mapping):
        raise OidcInvalidGrantError("授权码无效或已使用")
    try:
        return OidcCode(
            client_id=str(raw["client_id"]),
            redirect_uri=str(raw["redirect_uri"]),
            subject=str(raw["subject"]),
            tenant=str(raw["tenant"]),
            nonce=str(raw.get("nonce", "")),
            code_challenge=str(raw.get("code_challenge", "")),
            code_challenge_method=str(raw.get("code_challenge_method", "")),
            scope=str(raw.get("scope", "")),
            auth_time=int(cast("int", raw.get("auth_time", 0))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise OidcInvalidGrantError("授权码无效或已使用") from exc
