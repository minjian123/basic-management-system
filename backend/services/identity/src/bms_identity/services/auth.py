"""认证与身份服务 services 层：本地登录 / 刷新 / 登出编排。

- 登录：限流 → 验证码（按场景策略）→ org 凭据校验 → 签发双 token → 建会话（`sys_session` + Redis 标记）
  → 写回登录态；失败计数经限流基座（Redis 后端）累计，达阈值联动 `sys_user.locked_until`。
- 刷新：验签（`type=refresh`）→ 租户交叉校验 → 黑名单 → 会话标记 → 记录有效性 → `refresh_token_hash` 比对
  → 轮换（同会话 id，更新哈希）→ 重设 cookie。
- 登出：refresh 入黑名单 + 会话置 `revoked` + 删标记；幂等。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bms_core.captcha.base import BaseCaptcha, CaptchaCredential, CaptchaKind
from bms_core.core.base import BaseObject
from bms_core.core.config import LoginSettings, SessionSettings
from bms_core.core.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    AuthError,
    CaptchaVerifyError,
    LoginFailedError,
    ParamError,
)
from bms_core.core.logging import get_logger
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.oauth.user_token import (
    USER_TOKEN_TYPE_REFRESH,
    BaseUserTokenIssuer,
    UserTokenPair,
    UserTokenSpec,
)
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_core.security.base import BaseSessionSecurity
from bms_core.session.base import BaseSessionStore
from bms_core.ws.base import BaseRealtimePublisher
from bms_identity.repositories.session import SessionRepository
from bms_identity.schemas.auth import (
    CaptchaInput,
    LoginRequest,
    LoginResult,
    RefreshResult,
    UserSummary,
)
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.session import REASON_LOGOUT, SessionService

_ACCOUNT_DIMENSION = "account"
_IP_DIMENSION = "ip"
_FAIL_DIMENSION = "login-fail"
_LOGIN_SCENE = "login"

_LOGGER = get_logger("bms")


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _hash_token(token: str) -> str:
    """refresh token 哈希（SHA-256 hex；不落原始值）。

    Args:
        token: refresh token 紧凑串。

    Returns:
        str: 哈希（小写十六进制）。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LoginOutcome(BaseObject):
    """登录编排结果（含待下发 refresh cookie 的原始票据）。"""

    result: LoginResult
    refresh_token: str
    refresh_expires_in: int


@dataclass(frozen=True)
class RefreshOutcome(BaseObject):
    """刷新编排结果（含轮换后的 refresh 原始票据）。"""

    result: RefreshResult
    refresh_token: str
    refresh_expires_in: int


class LoginService(BaseObject):
    """本地登录 / 刷新 / 登出服务（请求级会话 + 各能力域）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        user_token_issuer: BaseUserTokenIssuer,
        session_security: BaseSessionSecurity,
        session_store: BaseSessionStore,
        captcha: BaseCaptcha,
        rate_limiter: BaseRateLimiter,
        org_client: OrgCredentialClient,
        login_settings: LoginSettings,
        session_settings: SessionSettings,
        realtime_publisher: BaseRealtimePublisher,
    ) -> None:
        """初始化。

        Args:
            session: 认证服务租户库会话。
            uow: 工作单元（写事务）。
            user_token_issuer: 用户双 token 签发者。
            session_security: 会话安全原语（会话 id / 黑名单键）。
            session_store: 会话标记存储。
            captcha: 验证码基座。
            rate_limiter: 限流基座（失败计数）。
            org_client: org 凭据接口客户端。
            login_settings: 登录防爆破配置。
            session_settings: 会话治理配置（多端上限）。
            realtime_publisher: 实时推送器（`session.revoked` 广播占位）。
        """
        self._session = session
        self._uow = uow
        self._sessions = SessionRepository(session)
        self._issuer = user_token_issuer
        self._security = session_security
        self._store = session_store
        self._captcha = captcha
        self._limiter = rate_limiter
        self._org = org_client
        self._login = login_settings
        self._session_settings = session_settings
        self._session_service = SessionService(
            session=session,
            uow=uow,
            security=session_security,
            store=session_store,
            publisher=realtime_publisher,
        )

    async def login(
        self,
        req: LoginRequest,
        *,
        tenant: str,
        ip: str | None,
        user_agent: str | None,
    ) -> LoginOutcome:
        """本地登录：校验 → 签发 → 建会话。

        Args:
            req: 登录请求。
            tenant: 生效租户编码。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。

        Returns:
            LoginOutcome: 登录结果（含 refresh 原始票据）。

        Raises:
            RateLimitError: 请求限流命中（10005/429）。
            CaptchaVerifyError: 验证码校验失败 / 需要验证码（20101）。
            AccountLockedError: 账号锁定（20003/401）。
            AccountDisabledError: 账号停用（20004/401）。
            LoginFailedError: 账号或密码错误（20002/401）。
            ServiceUnavailableError: org 凭据接口不可用（10007/503）。
        """
        await self._enforce_rate_limit(tenant, req.account, ip)
        await self._enforce_captcha(req.captcha)

        verified = await self._org.verify(tenant, req.account, req.password)
        if verified.locked:
            raise AccountLockedError()
        if not verified.found or not verified.valid:
            await self._record_failure(tenant, req.account)
        if verified.status != "enabled":
            raise AccountDisabledError()
        user = verified.user
        if user is None:  # pragma: no cover - found=True 必带用户概要
            raise AuthError("凭据校验结果缺少用户概要")

        session_id = self._security.new_session_id()
        pair = await self._issuer.issue_pair(
            UserTokenSpec(subject=str(user.id), session_id=session_id, tenant_id=tenant)
        )
        await self._session_service.enforce_max_active(
            user.id, tenant=tenant, max_active=self._session_settings.max_active
        )
        await self._persist_session(
            session_id=session_id,
            user_id=user.id,
            pair=pair,
            tenant=tenant,
            ip=ip,
            user_agent=user_agent,
        )
        await self._limiter.reset(self._fail_key(tenant, req.account))
        await self._org.login_state(tenant, req.account, success=True)
        return LoginOutcome(
            result=LoginResult(
                access_token=pair.access_token,
                token_type=pair.token_type,
                expires_in=pair.expires_in,
                user=UserSummary(
                    id=user.id,
                    username=user.username,
                    name=user.name,
                    tenant=tenant,
                    locale=user.locale,
                    timezone=user.timezone,
                ),
            ),
            refresh_token=pair.refresh_token,
            refresh_expires_in=pair.refresh_expires_in,
        )

    async def refresh(
        self,
        refresh_token: str,
        *,
        tenant: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> RefreshOutcome:
        """刷新轮换：校验 → 更新哈希与标记 → 签新双 token（同会话 id）。

        Args:
            refresh_token: cookie 中的 refresh token。
            tenant: 请求租户编码（来自子域名 / `X-Tenant-ID`）。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。

        Returns:
            RefreshOutcome: 轮换结果（含新 refresh 原始票据）。

        Raises:
            AuthError: 签名 / 类型 / 租户 / 黑名单 / 会话标记 / 哈希任一校验失败（20001/401）。
        """
        claims = self._issuer.verify(refresh_token, expected_type=USER_TOKEN_TYPE_REFRESH)
        payload = claims.payload
        token_tenant = payload.get("tenant_id")
        if not tenant or not token_tenant or token_tenant != tenant:
            raise AuthError("刷新令牌租户与请求租户不一致")
        session_id = payload.get("jti")
        if not session_id or not isinstance(session_id, str):
            raise AuthError("刷新令牌缺少会话标识")
        if await self._store.is_blacklisted(self._security.blacklist_key(session_id)):
            raise AuthError("刷新令牌已失效")
        if await self._store.load(session_id, tenant=tenant) is None:
            raise AuthError("会话已失效")

        async with self._uow.begin():
            record = await self._sessions.get_by_session_id(session_id)
            if record is None or record.revoked_at is not None or record.expires_at <= _utc_now():
                raise AuthError("会话已失效")
            if record.refresh_token_hash != _hash_token(refresh_token):
                raise AuthError("刷新令牌已失效")
            pair = await self._issuer.issue_pair(
                UserTokenSpec(subject=str(record.user_id), session_id=session_id, tenant_id=tenant)
            )
            await self._sessions.update_refresh_hash(session_id, _hash_token(pair.refresh_token))
        await self._store.save(
            session_id,
            {"user_id": record.user_id, "tenant": tenant, "ip": ip, "ua": user_agent},
            tenant=tenant,
            ttl=pair.refresh_expires_in,
        )
        return RefreshOutcome(
            result=RefreshResult(
                access_token=pair.access_token,
                token_type=pair.token_type,
                expires_in=pair.expires_in,
            ),
            refresh_token=pair.refresh_token,
            refresh_expires_in=pair.refresh_expires_in,
        )

    async def logout(self, refresh_token: str | None, *, tenant: str | None) -> None:
        """登出（幂等）：refresh 入黑名单 + 会话置撤销 + 删标记。

        Args:
            refresh_token: cookie 中的 refresh token；缺失即视为已登出。
            tenant: 请求租户编码。
        """
        if not refresh_token:  # pragma: no cover - 防御：路由侧已保证非空才调用
            return
        try:
            claims = self._issuer.verify(refresh_token, expected_type=USER_TOKEN_TYPE_REFRESH)
        except AuthError:
            return
        payload = claims.payload
        session_id = payload.get("jti")
        token_tenant = payload.get("tenant_id")
        if not session_id or not isinstance(session_id, str):
            return
        if token_tenant and tenant and token_tenant != tenant:
            return
        try:
            await self._session_service.revoke(session_id, tenant=tenant, reason=REASON_LOGOUT, broadcast=False)
        except Exception as exc:  # pragma: no cover - 登出尽力而为（幂等）
            _LOGGER.warning("登出清理未全部完成", session_id=session_id, error=str(exc))

    async def _enforce_rate_limit(self, tenant: str, account: str, ip: str | None) -> None:
        """请求限流：按 IP 与账号维度各校验一次。

        Args:
            tenant: 租户编码。
            account: 登录账号。
            ip: 客户端 IP（可选）。
        """
        if ip:
            await self._limiter.require(
                build_rate_limit_key(dimension=_IP_DIMENSION, target=ip, tenant=tenant),
                RateLimitRule(limit=self._login.ip_rate_limit),
            )
        await self._limiter.require(
            build_rate_limit_key(dimension=_ACCOUNT_DIMENSION, target=account, tenant=tenant),
            RateLimitRule(limit=self._login.account_rate_limit),
        )

    async def _enforce_captcha(self, captcha: CaptchaInput | None) -> None:
        """验证码：按场景策略强制或请求携带时校验。

        Args:
            captcha: 请求携带的验证码凭证（可选）。

        Raises:
            CaptchaVerifyError: 策略强制但未携带（20101）。
        """
        policy = await self._captcha.policy(_LOGIN_SCENE)
        if captcha is None:
            if policy.required:
                raise CaptchaVerifyError("需要验证码")
            return
        try:
            kind = CaptchaKind(captcha.kind)
        except ValueError as exc:
            raise ParamError(f"验证码形态非法：{captcha.kind}") from exc
        credential = CaptchaCredential(
            captcha_id=captcha.captcha_id,
            kind=kind,
            code=captcha.code,
            trace=tuple(captcha.trace),
            scene=_LOGIN_SCENE,
        )
        await self._captcha.require_credential(credential)

    async def _record_failure(self, tenant: str, account: str) -> None:
        """记录登录失败：Redis 计数递增，达阈值联动锁定并抛 20003。

        Args:
            tenant: 租户编码。
            account: 登录账号。

        Raises:
            AccountLockedError: 失败次数达阈值（20003/401）。
            LoginFailedError: 未达阈值（20002/401）。
        """
        decision = await self._limiter.check(
            self._fail_key(tenant, account),
            RateLimitRule(limit=self._login.max_failures, window=self._login.lock_seconds),
        )
        count = max(0, self._login.max_failures - decision.remaining)
        if decision.remaining == 0:
            await self._org.login_state(
                tenant, account, success=False, failed_count=count, lock_seconds=self._login.lock_seconds
            )
            raise AccountLockedError()
        await self._org.login_state(tenant, account, success=False, failed_count=count)
        raise LoginFailedError()

    async def _persist_session(
        self,
        *,
        session_id: str,
        user_id: int,
        pair: UserTokenPair,
        tenant: str,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        """写入会话记录与 Redis 标记（同会话 id）。

        Args:
            session_id: 会话 id。
            user_id: 用户 ID。
            pair: 双 token 签发结果。
            tenant: 租户编码。
            ip: 客户端 IP（可选）。
            user_agent: 客户端 User-Agent（可选）。
        """
        now = _utc_now()
        async with self._uow.begin():
            await self._sessions.create_session(
                session_id=session_id,
                user_id=user_id,
                refresh_token_hash=_hash_token(pair.refresh_token),
                login_at=now,
                expires_at=now + timedelta(seconds=pair.refresh_expires_in),
                device=_truncate(user_agent, 255),
                ip=_truncate(ip, 64),
            )
        await self._store.save(
            session_id,
            {"user_id": user_id, "tenant": tenant, "ip": ip, "ua": user_agent},
            tenant=tenant,
            ttl=pair.refresh_expires_in,
        )

    def _fail_key(self, tenant: str, account: str) -> str:
        """登录失败计数键。

        Args:
            tenant: 租户编码。
            account: 登录账号。

        Returns:
            str: 限流键。
        """
        return build_rate_limit_key(dimension=_FAIL_DIMENSION, target=account, tenant=tenant)


def _truncate(value: str | None, limit: int) -> str | None:
    """截断字符串到上限长度（None 原样）。

    Args:
        value: 原始值。
        limit: 最大长度。

    Returns:
        str | None: 截断后的值。
    """
    if value is None:
        return None
    return value[:limit]
