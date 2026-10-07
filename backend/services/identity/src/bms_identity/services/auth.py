"""认证与身份服务 services 层：本地登录 / 刷新 / 登出编排。

- 登录：限流 → 验证码（按场景策略）→ platform 凭据校验 → 签发双 token → 建会话（`sys_session` + Redis 标记）
  → 写回登录态；失败计数经限流基座（Redis 后端）累计，达阈值联动 `sys_user.locked_until`。
- 刷新：验签（`type=refresh`）→ 租户交叉校验 → 黑名单 → 会话标记 → 记录有效性 → `refresh_token_hash` 比对
  → 轮换（同会话 id，更新哈希）→ 重设 cookie。
- 登出：refresh 入黑名单 + 会话置 `revoked` + 删标记；幂等。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bms_core.captcha.base import BaseCaptcha, CaptchaCredential, CaptchaKind
from bms_core.core.concurrent import ConcurrentStableDict
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
from bms_core.core.objects import BaseFrameworkObject, BaseLoginResultContract
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.oauth.user_token import (
    USER_TOKEN_TYPE_REFRESH,
    BaseUserTokenIssuer,
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
from bms_identity.services.platform_client import PlatformCredentialClient
from bms_identity.services.session import REASON_LOGOUT, SessionService
from bms_identity.services.session_issuer import SessionIssuer, hash_refresh_token

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


@dataclass(frozen=True)
class LoginOutcome(BaseLoginResultContract):
    """登录编排结果（含待下发 refresh cookie 的原始票据）。"""

    result: LoginResult
    refresh_token: str
    refresh_expires_in: int
    remember_me: bool = True


@dataclass(frozen=True)
class RefreshOutcome(BaseLoginResultContract):
    """刷新编排结果（含轮换后的 refresh 原始票据）。"""

    result: RefreshResult
    refresh_token: str
    refresh_expires_in: int
    remember_me: bool = True


class LoginService(BaseFrameworkObject):
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
        platform_client: PlatformCredentialClient,
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
            platform_client: platform 凭据接口客户端。
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
        self._platform = platform_client
        self._login = login_settings
        self._session_settings = session_settings
        self._session_service = SessionService(
            session=session,
            uow=uow,
            security=session_security,
            store=session_store,
            publisher=realtime_publisher,
        )
        self._session_issuer = SessionIssuer(
            session=session,
            uow=uow,
            user_token_issuer=user_token_issuer,
            session_security=session_security,
            session_store=session_store,
            session_settings=session_settings,
            session_service=self._session_service,
        )

    async def login(
        self,
        req: LoginRequest,
        *,
        tenant_id: str,
        tenant_code: str,
        ip: str | None,
        user_agent: str | None,
    ) -> LoginOutcome:
        """本地登录：校验 → 签发 → 建会话。

        Args:
            req: 登录请求。
            tenant_id: 生效租户主键（雪花 id 字符串；令牌 / 会话 / 跨服务租户位 / 限流键）。
            tenant_code: 生效租户编码（响应展示）。
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
            ServiceUnavailableError: platform 凭据接口不可用（10007/503）。
        """
        await self._enforce_rate_limit(tenant_id, req.account, ip)
        await self._enforce_captcha(req.captcha, tenant_id=tenant_id, account=req.account)

        verified = await self._platform.verify(tenant_id, req.account, req.password)
        if verified.locked:
            raise AccountLockedError()
        if not verified.found or not verified.valid:
            await self._record_failure(tenant_id, req.account)
        if verified.status != "enabled":
            raise AccountDisabledError()
        user = verified.user
        if user is None:  # pragma: no cover - found=True 必带用户概要
            raise AuthError("凭据校验结果缺少用户概要")

        issued = await self._session_issuer.issue(
            user_id=user.id,
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            ip=ip,
            user_agent=user_agent,
            remember_me=req.remember_me,
        )
        await self._limiter.reset(self._fail_key(tenant_id, req.account))
        await self._platform.login_state(tenant_id, req.account, success=True)
        return LoginOutcome(
            result=LoginResult(
                access_token=issued.access_token,
                token_type=issued.token_type,
                expires_in=issued.access_expires_in,
                user=UserSummary(
                    id=user.id,
                    username=user.username,
                    name=user.name,
                    tenant=tenant_code,
                    locale=user.locale,
                    timezone=user.timezone,
                    must_change_password=verified.pwd_reset_required,
                ),
            ),
            refresh_token=issued.refresh_token,
            refresh_expires_in=issued.refresh_expires_in,
            remember_me=issued.remember_me,
        )

    async def refresh(
        self,
        refresh_token: str,
        *,
        tenant_id: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> RefreshOutcome:
        """刷新轮换：校验 → 更新哈希与标记 → 签新双 token（同会话 id）。

        Args:
            refresh_token: cookie 中的 refresh token。
            tenant_id: 请求租户主键（来自子域名 / `X-Tenant-ID` 解析后的雪花 id 字符串）。
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
        if not tenant_id or not token_tenant or token_tenant != tenant_id:
            raise AuthError("刷新令牌租户与请求租户不一致")
        session_id = payload.get("jti")
        if not session_id or not isinstance(session_id, str):
            raise AuthError("刷新令牌缺少会话标识")
        if await self._store.is_blacklisted(self._security.blacklist_key(session_id)):
            raise AuthError("刷新令牌已失效")
        if await self._store.load(session_id, tenant=tenant_id) is None:
            raise AuthError("会话已失效")

        async with self._uow.begin():
            record = await self._sessions.get_by_session_id(session_id)
            if record is None or record.revoked_at is not None or record.expires_at <= _utc_now():
                raise AuthError("会话已失效")
            if record.refresh_token_hash != hash_refresh_token(refresh_token):
                raise AuthError("刷新令牌已失效")
            remembered = record.remember_me is not False
            pair = await self._issuer.issue_pair(
                UserTokenSpec(
                    subject=str(record.user_id),
                    session_id=session_id,
                    tenant_id=tenant_id,
                    remember_me=remembered,
                )
            )
            await self._sessions.rotate(
                session_id,
                refresh_token_hash=hash_refresh_token(pair.refresh_token),
                expires_at=_utc_now() + timedelta(seconds=pair.refresh_expires_in),
            )
        await self._store.save(
            session_id,
            ConcurrentStableDict({"user_id": record.user_id, "tenant": tenant_id, "ip": ip, "ua": user_agent}),
            tenant=tenant_id,
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
            remember_me=remembered,
        )

    async def logout(self, refresh_token: str | None, *, tenant_id: str | None) -> None:
        """登出（幂等）：refresh 入黑名单 + 会话置撤销 + 删标记。

        Args:
            refresh_token: cookie 中的 refresh token；缺失即视为已登出。
            tenant_id: 请求租户主键（雪花 id 字符串）。
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
        if token_tenant and tenant_id and token_tenant != tenant_id:
            return
        try:
            await self._session_service.revoke(session_id, tenant=tenant_id, reason=REASON_LOGOUT, broadcast=False)
        except Exception as exc:  # pragma: no cover - 登出尽力而为（幂等）
            _LOGGER.warning("登出清理未全部完成", session_id=session_id, error=str(exc))

    async def _enforce_rate_limit(self, tenant_id: str, account: str, ip: str | None) -> None:
        """请求限流：按 IP 与账号维度各校验一次。

        Args:
            tenant_id: 租户主键（限流键租户位）。
            account: 登录账号。
            ip: 客户端 IP（可选）。
        """
        if ip:
            await self._limiter.require(
                build_rate_limit_key(dimension=_IP_DIMENSION, target=ip, tenant=tenant_id),
                RateLimitRule(limit=self._login.ip_rate_limit),
            )
        await self._limiter.require(
            build_rate_limit_key(dimension=_ACCOUNT_DIMENSION, target=account, tenant=tenant_id),
            RateLimitRule(limit=self._login.account_rate_limit),
        )

    async def _enforce_captcha(self, captcha: CaptchaInput | None, *, tenant_id: str, account: str) -> None:
        """验证码：按场景策略强制，或连续失败达阈值强制，或请求携带时校验。

        Args:
            captcha: 请求携带的验证码凭证（可选）。
            tenant_id: 租户主键（失败计数键作用域）。
            account: 登录账号（失败计数键目标）。

        Raises:
            CaptchaVerifyError: 策略 / 阈值强制但未携带（20101）。
        """
        policy = await self._captcha.policy(_LOGIN_SCENE)
        fails = await self._limiter.peek(self._fail_key(tenant_id, account))
        required = policy.required or (policy.fail_threshold > 0 and fails >= policy.fail_threshold)
        if captcha is None:
            if required:
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

    async def _record_failure(self, tenant_id: str, account: str) -> None:
        """记录登录失败：Redis 计数递增，达阈值联动锁定并抛 20003。

        Args:
            tenant_id: 租户主键（失败计数键作用域；platform 登录态经服务 JWT 租户位）。
            account: 登录账号。

        Raises:
            AccountLockedError: 失败次数达阈值（20003/401）。
            LoginFailedError: 未达阈值（20002/401）。
        """
        decision = await self._limiter.check(
            self._fail_key(tenant_id, account),
            RateLimitRule(limit=self._login.max_failures, window=self._login.lock_seconds),
        )
        count = max(0, self._login.max_failures - decision.remaining)
        if decision.remaining == 0:
            await self._platform.login_state(
                tenant_id, account, success=False, failed_count=count, lock_seconds=self._login.lock_seconds
            )
            raise AccountLockedError()
        await self._platform.login_state(tenant_id, account, success=False, failed_count=count)
        raise LoginFailedError()

    def _fail_key(self, tenant_id: str, account: str) -> str:
        """登录失败计数键（限流键租户位 = 租户主键）。

        Args:
            tenant_id: 租户主键（雪花 id 字符串）。
            account: 登录账号。

        Returns:
            str: 限流键。
        """
        return build_rate_limit_key(dimension=_FAIL_DIMENSION, target=account, tenant=tenant_id)


class CurrentUserService(BaseFrameworkObject):
    """当前用户概要服务：经 platform 内部用户接口取概要（首屏静默续期恢复用户上下文）。

    不依赖认证服务租户库会话——用户概要与强制改密标记归属 platform 服务，本服务只做**取数与映射**
    （与登录响应的 `UserSummary` 同字段、同语义）。
    """

    def __init__(self, platform_client: PlatformCredentialClient) -> None:
        """初始化。

        Args:
            platform_client: platform 内部接口客户端（复用登录链路同一客户端）。
        """
        self._platform = platform_client

    async def current_user(self, *, user_id: int | None, tenant_id: str | None, tenant_code: str | None) -> UserSummary:
        """取当前登录用户概要。

        Args:
            user_id: 当前登录主体用户主键（`AuthContext.user_id`）。
            tenant_id: 生效租户主键（雪花 id 字符串；跨服务租户位）。
            tenant_code: 生效租户编码（响应展示）。

        Returns:
            UserSummary: 用户概要（含 `must_change_password`）。

        Raises:
            AuthError: 缺少用户标识 / 用户不存在（20001/401，按登录态失效处理）。
            AccountDisabledError: 账号已停用（20004/401）。
            ServiceUnavailableError: platform 不可达 / 响应契约非法（10007/503，fail-closed）。
        """
        if user_id is None:
            raise AuthError("缺少用户标识")
        profile = await self._platform.user_profile(tenant_id, user_id)
        if not profile.found or profile.user is None:
            raise AuthError("用户不存在")
        user = profile.user
        if user.status != "enabled":
            raise AccountDisabledError()
        return UserSummary(
            id=user.id,
            username=user.username,
            name=user.name,
            tenant=tenant_code,
            locale=user.locale,
            timezone=user.timezone,
            must_change_password=user.pwd_reset_required,
        )
