"""认证与身份服务 services 层：SSO 登录编排（入口清单 / 授权跳转 / 回调闭环）。

- 入口清单：租户内 `enabled` IdP 行 → 前端渲染登录方式。
- 授权跳转：生成 `state / nonce / code_verifier`（PKCE S256）落流程状态存储（短 TTL、一次性），
  构造外部授权 URL；IdP 发现失败翻译为 `20053`。
- 回调闭环：`state` 一次性消费（记录租户为权威）→ 换码 → ID Token 验签 / `nonce` 校验
  （无 `id_token` 回退 userinfo）→ `sys_user_identity` 映射 → org 用户概要 → `SessionIssuer`
  签发同构会话 → org `login-state(success=True)`。
- 错误翻译：`bms_core` 出站失败（`ServiceUnavailableError`）在服务边界翻译为
  `SsoProviderUnavailableError`（`20053`）；`state` / `nonce` / PKCE / 令牌校验失败为 `20052`；
  映射未命中为 `20054`；账号停用复用 `20004`。
- 日志：结构化 `warning`（`idp_key` / `tenant` / `code` / `error`），`state` 只记前 8 位脱敏，
  不落 token / code / secret。
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import ClassVar, cast
from urllib.parse import quote

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import SsoSettings
from bms_core.core.exceptions import (
    AccountDisabledError,
    AuthError,
    ConfigError,
    EnterpriseIdpError,
    ServiceUnavailableError,
    SsoCallbackError,
    SsoIdentityUnmatchedError,
    SsoProviderNotFoundError,
    SsoProviderUnavailableError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseAuthorizeUrlResultContract, BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.idp.base import BaseIdentityProvider, IdentityToken
from bms_core.idp.state.base import BaseIdpStateStore, IdpFlowState
from bms_core.lock.base import BaseDistributedLock
from bms_core.outbox.base import BaseOutboxStore
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_identity.repositories.identity_provider import IdentityProviderRepository
from bms_identity.repositories.user_identity import UserIdentityRepository
from bms_identity.schemas.sso import SsoProviderItem
from bms_identity.services.jit import ExternalIdentity, JitService
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.provider_registry import ProviderRegistry
from bms_identity.services.session_issuer import IssuedSession, SessionIssuer

__all__ = ["SsoLoginResult", "SsoService"]

_IP_DIMENSION = "ip"
_CLIENT_DIMENSION = "client"
_PKCE_METHOD = "S256"

_LOGGER = get_logger("bms")


@dataclass(frozen=True)
class SsoLoginResult(BaseValueObject):
    """SSO 回调成功结果（租户编码 + 已签发会话）。"""

    tenant_code: str
    """登录生效租户编码（以流程状态记录为权威；对外展示 / 回跳）。"""

    issued: IssuedSession
    """已签发的会话（双 token + 会话 id）。"""


@dataclass(frozen=True)
class SsoAuthorizeResult(BaseAuthorizeUrlResultContract):
    """授权跳转结果（授权 URL + 流程状态，供 302 跳转或 JSON 返回）。"""

    URL_FIELD: ClassVar[str] = "authorize_url"

    authorize_url: str
    """外部授权入口 URL。"""

    state: str
    """流程状态（一次性；前端渲染二维码 / 初始化平台组件后可回传回调）。"""

    expires_in: int
    """流程状态有效期（秒；与流程状态存储 TTL 一致）。"""


class SsoService(BaseFrameworkObject):
    """SSO 编排服务（流程状态 / 限流 / IdP 实例 / org 概要）。"""

    def __init__(
        self,
        *,
        state_store: BaseIdpStateStore,
        rate_limiter: BaseRateLimiter,
        org_client: OrgCredentialClient,
        provider_registry: ProviderRegistry,
        sso_settings: SsoSettings,
        lock: BaseDistributedLock,
        outbox_store: BaseOutboxStore,
    ) -> None:
        """初始化。

        Args:
            state_store: 流程状态存储（state / nonce / PKCE 一次性）。
            rate_limiter: 限流基座（authorize / callback）。
            org_client: org 内部接口客户端（用户概要 / 登录态写回 / 建号）。
            provider_registry: IdP 行实例化桥接。
            sso_settings: SSO 配置（TTL / 限流阈值 / PKCE 开关 / JIT）。
            lock: 分布式锁（JIT 临界区串行化）。
            outbox_store: 事务性发件箱（JIT 首登建号事件）。
        """
        self._state = state_store
        self._limiter = rate_limiter
        self._org = org_client
        self._providers = provider_registry
        self._sso = sso_settings
        self._jit = JitService(
            lock=lock,
            org_client=org_client,
            outbox_store=outbox_store,
            sso_settings=sso_settings,
        )

    async def list_providers(self, tenant: str, session: DbSession) -> list[SsoProviderItem]:
        """可用 IdP 清单（仅 `enabled`，按 `sort` / `id` 升序）。

        Args:
            tenant: 租户编码（保留参数，仓储已按当前租户库取数）。
            session: 认证服务租户库会话。

        Returns:
            list[SsoProviderItem]: 入口清单项（租户无启用 IdP 时为空列表）。
        """
        rows = await IdentityProviderRepository(session).list_enabled()
        return [
            SsoProviderItem(
                idp_key=row.idp_key,
                name=row.name,
                icon=row.icon or "",
                type=row.type,
                sort=row.sort,
            )
            for row in rows
        ]

    async def authorize(
        self,
        idp_key: str,
        *,
        tenant_id: str,
        tenant_code: str,
        ip: str | None,
        session: DbSession,
    ) -> str:
        """生成流程状态并返回外部授权 URL（302 跳转形态）。

        Args:
            idp_key: 租户内 IdP 标识。
            tenant_id: 生效租户主键（雪花 id 字符串；内部键依据）。
            tenant_code: 生效租户编码（对外展示 / 校验）。
            ip: 客户端 IP（可选；限流维度）。
            session: 认证服务租户库会话。

        Returns:
            str: 外部授权端点 URL（302 Location）。

        Raises:
            SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
            SsoProviderUnavailableError: 配置缺失 / IdP 发现失败（20053/503）。
            EnterpriseIdpError: 企微 / 钉钉专用失败（20057~20062）。
            RateLimitError: 限流命中（10005/429）。
        """
        result = await self.authorize_info(
            idp_key, tenant_id=tenant_id, tenant_code=tenant_code, ip=ip, session=session
        )
        return result.authorize_url

    async def authorize_info(
        self,
        idp_key: str,
        *,
        tenant_id: str,
        tenant_code: str,
        ip: str | None,
        session: DbSession,
    ) -> SsoAuthorizeResult:
        """生成流程状态并返回授权 URL / 状态 / 有效期（供 JSON 形态消费）。

        Args:
            idp_key: 租户内 IdP 标识。
            tenant_id: 生效租户主键（雪花 id 字符串；内部键依据）。
            tenant_code: 生效租户编码（对外展示 / 校验）。
            ip: 客户端 IP（可选；限流维度）。
            session: 认证服务租户库会话。

        Returns:
            SsoAuthorizeResult: 授权 URL、流程状态与有效期。

        Raises:
            SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
            SsoProviderUnavailableError: 配置缺失 / IdP 发现失败（20053/503）。
            EnterpriseIdpError: 企微 / 钉钉专用失败（20057~20062）。
            RateLimitError: 限流命中（10005/429）。
        """
        await self._enforce_authorize_rate_limit(tenant_id, idp_key, ip)
        row = await IdentityProviderRepository(session).get_by_key(idp_key)
        if row is None or row.status != "enabled":
            raise SsoProviderNotFoundError()

        try:
            instance = self._providers.instance_for(row)
        except ConfigError as exc:
            _LOGGER.warning("SSO 授权配置不可用", idp_key=idp_key, tenant=tenant_code, error=str(exc))
            raise SsoProviderUnavailableError("IdP 配置不可用") from exc

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)
        verifier = secrets.token_urlsafe(64) if self._sso.pkce else ""
        flow = IdpFlowState(
            tenant_code=tenant_code,
            tenant_id=tenant_id,
            idp_key=idp_key,
            nonce=nonce,
            code_verifier=verifier,
            redirect_uri=self._providers.redirect_uri_for(row),
            created_at=datetime.now(UTC).isoformat(),
        )
        await self._state.save(
            state,
            ConcurrentStableDict(_flow_payload(flow)),
            ttl=self._sso.state_ttl_seconds,
        )
        try:
            authorize_url = await instance.authorize(
                state,
                nonce=nonce,
                code_challenge=_code_challenge(verifier) if verifier else None,
                code_challenge_method=_PKCE_METHOD if verifier else None,
                service=_build_service_url(flow.redirect_uri, state),
            )
        except ServiceUnavailableError as exc:
            await self._state.delete(state)
            _LOGGER.warning("SSO 授权跳转失败", idp_key=idp_key, tenant=tenant_code, error=str(exc))
            raise SsoProviderUnavailableError("IdP 暂不可用") from exc
        return SsoAuthorizeResult(
            authorize_url=authorize_url,
            state=state,
            expires_in=self._sso.state_ttl_seconds,
        )

    async def consume_flow(
        self,
        state: str,
        *,
        idp_key: str,
        tenant_code: str | None,
        ip: str | None,
    ) -> IdpFlowState:
        """一次性消费流程状态并校验（回调租户以记录为权威）。

        Args:
            state: IdP 回传的流程状态。
            idp_key: 回调路径中的 IdP 标识（须与记录一致）。
            tenant_code: 请求上下文租户编码（有则须与记录一致）。
            ip: 客户端 IP（可选；限流维度）。

        Returns:
            IdpFlowState: 流程记录（租户 / `nonce` / PKCE 校验码）。

        Raises:
            SsoCallbackError: `state` 缺失 / 过期 / 重放 / 与路径或上下文租户不符（20052/400）。
            RateLimitError: 限流命中（10005/429）。
        """
        await self._enforce_callback_rate_limit(ip)
        payload = await self._state.consume(state)
        if payload is None:
            _LOGGER.warning("SSO 流程状态无效", state=state[:8], idp_key=idp_key)
            raise SsoCallbackError("流程状态无效或已过期")
        flow = _flow_from_payload(payload)
        if flow.idp_key != idp_key:
            _LOGGER.warning("SSO 流程状态与身份源不匹配", state=state[:8], idp_key=idp_key)
            raise SsoCallbackError("流程状态与身份源不匹配")
        if tenant_code and tenant_code != flow.tenant_code:
            _LOGGER.warning("SSO 流程租户不一致", state=state[:8], tenant=flow.tenant_code, idp_key=idp_key)
            raise SsoCallbackError("租户与流程状态不一致")
        return flow

    async def callback(
        self,
        flow: IdpFlowState,
        *,
        idp_key: str,
        code: str | None,
        error: str | None,
        ip: str | None,
        user_agent: str | None,
        session: DbSession,
        platform_session: DbSession,
        session_issuer: SessionIssuer,
        state: str = "",
    ) -> SsoLoginResult:
        """回调闭环：换码 / 验签 / 映射 / 概要 → 签发会话。

        读取身份源行后释放只读事务，确保会话签发从干净事务边界开始（与本地登录同口径）。

        Args:
            flow: 已消费的流程记录。
            idp_key: 回调路径中的 IdP 标识。
            code: 授权码（IdP 回传；CAS 为服务票据 `ticket`）。
            error: IdP 回传错误（如 `access_denied`）。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。
            session: 认证服务租户库会话（按流程租户开启）。
            platform_session: 平台库会话（身份映射只读 / JIT 可写）。
            session_issuer: 会话签发作构件。
            state: 回调回传的流程状态（CAS 重建 `service` 用；与登录时一致）。

        Returns:
            SsoLoginResult: 登录结果（租户 + 会话）。

        Raises:
            SsoCallbackError: IdP 拒绝 / 缺授权码 / 令牌（票据）校验失败（20052/400）。
            SsoProviderNotFoundError: IdP 不存在或已停用（20051/404）。
            SsoProviderUnavailableError: IdP 换码 / 校验 / 用户信息不可达（20053/503）。
            SsoIdentityUnmatchedError: 映射未命中或本地用户不存在（20054/403）。
            SsoIdentityConflictError: 身份映射冲突（20055/409）。
            AccountDisabledError: 本地账号停用（20004/401）。
            ServiceUnavailableError: org 概要 / 登录态接口不可用（10007/503）。
        """
        if error:
            _LOGGER.warning("SSO 回调被 IdP 拒绝", idp_key=idp_key, tenant=flow.tenant_code, error=error)
            raise SsoCallbackError(f"IdP 返回错误：{error}")
        if not code:
            raise SsoCallbackError("缺少授权码")

        row = await IdentityProviderRepository(session).get_by_key(idp_key)
        if row is None or row.status != "enabled":
            raise SsoProviderNotFoundError()
        try:
            instance = self._providers.instance_for(row)
        except ConfigError as exc:
            raise SsoProviderUnavailableError("IdP 配置不可用") from exc
        provider_config = row.config
        await session.rollback()

        token = await self._exchange(
            instance,
            code,
            flow,
            idp_key,
            service=_build_service_url(flow.redirect_uri, state),
        )
        identity = await self._resolve_identity(instance, token, flow, idp_key)
        user_id = await self._resolve_user_id(
            flow=flow,
            idp_key=idp_key,
            provider_config=provider_config,
            identity=identity,
            platform_session=platform_session,
        )
        profile = await self._org.user_profile(flow.tenant_id, user_id)
        if not profile.found or profile.user is None:
            _LOGGER.warning("SSO 本地用户不存在", idp_key=idp_key, tenant=flow.tenant_code, user_id=user_id)
            raise SsoIdentityUnmatchedError()
        if profile.user.status != "enabled":
            raise AccountDisabledError()

        issued = await session_issuer.issue(
            user_id=user_id,
            tenant_id=flow.tenant_id,
            tenant_code=flow.tenant_code,
            ip=ip,
            user_agent=user_agent,
        )
        await self._org.login_state(flow.tenant_id, profile.user.username, success=True)
        _LOGGER.info("SSO 登录成功", idp_key=idp_key, tenant=flow.tenant_code, user_id=user_id)
        return SsoLoginResult(tenant_code=flow.tenant_code, issued=issued)

    async def _resolve_user_id(
        self,
        *,
        flow: IdpFlowState,
        idp_key: str,
        provider_config: str,
        identity: ExternalIdentity,
        platform_session: DbSession,
    ) -> int:
        """定位本地用户：命中映射直接复用，未命中且 JIT 启用则自动建号。

        Args:
            flow: 流程记录。
            idp_key: IdP 标识。
            provider_config: IdP 行配置 JSON 原文（JIT 开关来源；行会话已释放，传值）。
            identity: 外部身份声明。
            platform_session: 平台库会话（可写，JIT 需要）。

        Returns:
            int: 本地用户主键。

        Raises:
            SsoIdentityUnmatchedError: 未匹配且 JIT 未启用 / 被拒（20054/403）。
            SsoIdentityConflictError: JIT 锁或映射冲突（20055/409）。
            SsoProviderUnavailableError: org 建号接口不可达（20053/503）。
        """
        mapping = await UserIdentityRepository(platform_session).get_by_key_external(
            f"{flow.tenant_id}:{idp_key}", identity.subject
        )
        if mapping is not None:
            if str(mapping.tenant_id) == flow.tenant_id:
                return mapping.user_id
            _LOGGER.warning("SSO 身份映射租户不一致", idp_key=idp_key, tenant=flow.tenant_code)
            raise SsoIdentityUnmatchedError()
        if not self._jit.enabled(provider_config):
            _LOGGER.warning("SSO 身份未匹配", idp_key=idp_key, tenant=flow.tenant_code)
            raise SsoIdentityUnmatchedError()
        result = await self._jit.provision(
            tenant_id=flow.tenant_id,
            tenant_code=flow.tenant_code,
            idp_key=idp_key,
            config=provider_config,
            identity=identity,
            platform_session=platform_session,
        )
        return result.user_id

    async def _exchange(
        self,
        instance: BaseIdentityProvider,
        code: str,
        flow: IdpFlowState,
        idp_key: str,
        *,
        service: str,
    ) -> IdentityToken:
        """换码（OIDC 带 PKCE）或票据校验（CAS），出站失败翻译为 `20053`、票据校验失败 `20052`。

        Args:
            instance: IdP 实例。
            code: 授权码（CAS 为服务票据）。
            flow: 流程记录（PKCE 校验码）。
            idp_key: IdP 标识（日志）。
            service: 服务地址（CAS 校验；OIDC 忽略）。

        Returns:
            IdentityToken: 令牌响应（OIDC 含 `id_token`；CAS 含 `identity`）。

        Raises:
            SsoProviderUnavailableError: IdP 换码 / 校验不可达或配置不可用（20053/503）。
            SsoCallbackError: 票据校验失败（CAS `authenticationFailure`；20052/400）。
        """
        try:
            return await instance.exchange_token(
                code,
                code_verifier=flow.code_verifier or None,
                service=service or None,
            )
        except EnterpriseIdpError:
            raise
        except ServiceUnavailableError as exc:
            _LOGGER.warning("SSO 换码失败", idp_key=idp_key, tenant=flow.tenant_code, error=str(exc))
            raise SsoProviderUnavailableError("IdP 换码失败") from exc
        except AuthError as exc:
            _LOGGER.warning("SSO 票据校验失败", idp_key=idp_key, tenant=flow.tenant_code, error=str(exc))
            raise SsoCallbackError("票据校验失败") from exc
        except ConfigError as exc:
            raise SsoProviderUnavailableError("IdP 配置不可用") from exc

    async def _resolve_identity(
        self,
        instance: BaseIdentityProvider,
        token: IdentityToken,
        flow: IdpFlowState,
        idp_key: str,
    ) -> ExternalIdentity:
        """解析外部身份声明：CAS 直接回填 → 优先 ID Token 验签（含 `nonce`）→ 回退 userinfo。

        Args:
            instance: IdP 实例。
            token: 令牌响应。
            flow: 流程记录（`nonce`）。
            idp_key: IdP 标识（日志）。

        Returns:
            ExternalIdentity: 归一化外部身份（主体 / 用户名 / 显示名 / 邮箱 / 语言时区）。

        Raises:
            SsoCallbackError: ID Token 签名 / `nonce` / 过期等校验失败（20052/400）。
            SsoProviderUnavailableError: JWKS / userinfo 不可达（20053/503）。
        """
        if token.identity is not None:
            identity = token.identity
            return ExternalIdentity(
                subject=identity.subject,
                username=identity.username,
                name=identity.name or identity.username,
                email=identity.email,
            )
        if token.id_token:
            try:
                claims = await instance.verify_token(token.id_token, nonce=flow.nonce or None)
            except AuthError as exc:
                _LOGGER.warning("SSO ID Token 校验失败", idp_key=idp_key, tenant=flow.tenant_code, error=str(exc))
                raise SsoCallbackError("ID Token 校验失败") from exc
            except ServiceUnavailableError as exc:
                raise SsoProviderUnavailableError("IdP 验签不可用") from exc
            except ConfigError as exc:
                raise SsoProviderUnavailableError("IdP 配置不可用") from exc
            payload = claims.payload
            return ExternalIdentity(
                subject=claims.subject,
                username=_as_str(payload.get("preferred_username")),
                name=_as_str(payload.get("name")),
                email=_as_str(payload.get("email")) or None,
                locale=_as_str(payload.get("locale")) or None,
                timezone=_as_str(payload.get("zoneinfo")) or None,
            )

        try:
            user = await instance.userinfo(token.access_token)
        except ServiceUnavailableError as exc:
            raise SsoProviderUnavailableError("IdP 用户信息不可用") from exc
        return ExternalIdentity(
            subject=user.subject,
            username=user.username,
            name=user.username,
            email=user.email,
        )

    async def _enforce_authorize_rate_limit(self, tenant_id: str, idp_key: str, ip: str | None) -> None:
        """authorize 限流：IP 维度 + client 维度（target=`idp_key`）。

        Args:
            tenant_id: 租户主键（雪花 id 字符串；限流键租户位）。
            idp_key: IdP 标识。
            ip: 客户端 IP（可选）。
        """
        if ip:
            await self._limiter.require(
                build_rate_limit_key(dimension=_IP_DIMENSION, target=ip, tenant=tenant_id),
                RateLimitRule(limit=self._sso.ip_rate_limit),
            )
        await self._limiter.require(
            build_rate_limit_key(dimension=_CLIENT_DIMENSION, target=idp_key, tenant=tenant_id),
            RateLimitRule(limit=self._sso.provider_rate_limit),
        )

    async def _enforce_callback_rate_limit(self, ip: str | None) -> None:
        """callback 限流：IP 维度（租户未知，键为全局）。

        Args:
            ip: 客户端 IP（可选）。
        """
        if ip:
            await self._limiter.require(
                build_rate_limit_key(dimension=_IP_DIMENSION, target=ip),
                RateLimitRule(limit=self._sso.ip_rate_limit),
            )


def _as_str(value: object) -> str:
    """取声明中的字符串值（非字符串 / 缺失返回空串）。

    Args:
        value: claim 值。

    Returns:
        str: 字符串值；非字符串返回空串。
    """
    return value if isinstance(value, str) else ""


def _build_service_url(redirect_uri: str, state: str) -> str:
    """构造 CAS `service`（登录跳转与票据校验两处使用，保证完全一致）。

    Args:
        redirect_uri: 回调地址（行配置或按基址派生）。
        state: 流程状态。

    Returns:
        str: `{redirect_uri}?state={state}`（`redirect_uri` 已含查询串时以 `&` 追加）；无回调地址返回空串。
    """
    if not redirect_uri:
        return ""
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}state={quote(state, safe='')}"


def _code_challenge(verifier: str) -> str:
    """PKCE S256 挑战值：`BASE64URL(SHA256(verifier))`（去填充）。

    Args:
        verifier: code_verifier 原文。

    Returns:
        str: code_challenge。
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _flow_payload(flow: IdpFlowState) -> dict[str, object]:
    """流程记录 → 存储 payload（JSON 序列化口径）。

    Args:
        flow: 流程记录。

    Returns:
        dict[str, object]: payload。
    """
    return cast("dict[str, object]", asdict(flow))


def _flow_from_payload(payload: object) -> IdpFlowState:
    """存储 payload → 流程记录（非法结构按流程失效处理）。

    Args:
        payload: 存储返回值。

    Returns:
        IdpFlowState: 流程记录。

    Raises:
        SsoCallbackError: payload 结构非法（20052/400）。
    """
    if not isinstance(payload, Mapping):
        raise SsoCallbackError("流程状态无效或已过期")
    values = cast("Mapping[str, object]", payload)
    try:
        return IdpFlowState(
            tenant_code=str(values["tenant_code"]),
            tenant_id=str(values["tenant_id"]),
            idp_key=str(values["idp_key"]),
            nonce=str(values["nonce"]),
            code_verifier=str(values["code_verifier"]),
            redirect_uri=str(values["redirect_uri"]),
            created_at=str(values["created_at"]),
        )
    except KeyError as exc:
        raise SsoCallbackError("流程状态无效或已过期") from exc
