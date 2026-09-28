"""认证与身份服务 services 层：自助找回密码编排（发起 / 重置）。

- 发起：IP 限流 → 验证码（场景 `reset_password`，一次性消费）→ 标识 / 用户限流 → org 解析投递目标
  （账号 / 手机 / 邮箱取通道）→ 生成高熵重置 token 落流程状态存储（命名空间 `pwdreset`，TTL 15 分钟）
  → 经 `BaseNotifier` 占位发送（邮件 / 短信；真实渠道归阶段八）。成功路径**恒同响应**（防枚举），
  账号不存在 / 停用 / 无通道一律不发送。
- 重置：流程状态**先一次性消费**（`GETDEL`）→ org 改密（强制过密码策略，消费 03_05 语义）→
  按用户批量撤销全部在线会话（refresh 黑名单 + Redis 标记清理 + `session.revoked` 广播）。
- 安全口径：token / 密码明文不落日志、不回显响应；Redis / 通知 / org 不可用一律 fail-closed（10007）。
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping

from bms_core.captcha.base import BaseCaptcha, CaptchaCredential, CaptchaKind
from bms_core.core.config import PasswordResetSettings
from bms_core.core.exceptions import (
    CaptchaVerifyError,
    ParamError,
    PasswordResetTokenError,
    PasswordResetTooFrequentError,
    ServiceUnavailableError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.idp.state.base import BaseIdpStateStore
from bms_core.notify.base import BaseNotifier, NotificationMessage, NotifyChannel
from bms_core.ratelimit.base import BaseRateLimiter, RateLimitRule, build_rate_limit_key
from bms_identity.schemas.auth import CaptchaInput
from bms_identity.schemas.password_reset import (
    OrgResetTargetResult,
    PasswordForgotResult,
    PasswordResetResult,
)
from bms_identity.services.org_client import OrgCredentialClient
from bms_identity.services.session import REASON_PASSWORD_RESET, SessionService

PASSWORD_RESET_NAMESPACE = "pwdreset"
"""流程状态命名空间：重置 token（与 SSO `idpstate` / OIDC `oidccode` 隔离）。"""

_RESET_SCENE = "reset_password"
"""找回密码验证码场景（策略默认强制；渠道降级顺序见 03_04）。"""

_IP_DIMENSION = "password-reset-ip"
"""IP 维度限流键名。"""

_IDENTIFIER_DIMENSION = "password-reset"
"""标识（账号 / 手机 / 邮箱）维度限流键名。"""

_USER_DIMENSION = "password-reset-user"
"""用户维度限流键名（命中账号后追加，防多标识绕过）。"""

_LOGGER = get_logger("bms")


class PasswordResetService(BaseFrameworkObject):
    """自助找回密码服务：发起（验证码 / 限流 / token / 通知）与重置（改密 / 会话全失效）。"""

    def __init__(
        self,
        *,
        org_client: OrgCredentialClient,
        captcha: BaseCaptcha,
        rate_limiter: BaseRateLimiter,
        state_store: BaseIdpStateStore,
        notifier: BaseNotifier,
        session_service: SessionService,
        settings: PasswordResetSettings,
    ) -> None:
        """初始化。

        Args:
            org_client: org 凭据接口客户端（解析投递目标 / 改密）。
            captcha: 验证码基座（场景策略与凭证校验）。
            rate_limiter: 限流基座（账号 / IP / 用户维度）。
            state_store: 流程状态存储（重置 token 一次性存取）。
            notifier: 通知基座（占位发送；真实渠道归阶段八）。
            session_service: 会话服务（按用户批量撤销）。
            settings: 找回密码配置（token TTL / 限流阈值 / 重置链接基址）。
        """
        self._org = org_client
        self._captcha = captcha
        self._limiter = rate_limiter
        self._state = state_store
        self._notifier = notifier
        self._sessions = session_service
        self._settings = settings

    async def request_reset(
        self,
        identifier: str,
        captcha: CaptchaInput | None,
        *,
        tenant_id: str,
        tenant_code: str,
        ip: str | None,
    ) -> PasswordForgotResult:
        """发起找回：限流 → 验证码 → 解析目标 → 写 token → 占位发送。

        Args:
            identifier: 账号 / 手机号 / 邮箱。
            captcha: 验证码凭证（可选；场景策略强制时必带）。
            tenant_id: 租户主键（雪花 id 字符串；限流键 / token 存储键与 org 调用依据）。
            tenant_code: 租户编码（重置链接 / 展示）。
            ip: 客户端 IP（可选；缺失跳过 IP 维度限流）。

        Returns:
            PasswordForgotResult: 恒 `sent=True`（存在性 / 通道差异不回显）。

        Raises:
            PasswordResetTooFrequentError: 限流命中（20006/429）。
            CaptchaVerifyError: 验证码需要 / 校验不通过（20101）。
            ParamError: 验证码形态非法（10001）。
            ServiceUnavailableError: org / Redis / 通知渠道不可用（10007/503）。
        """
        await self._enforce_ip_limit(tenant_id, ip)
        await self._enforce_captcha(captcha)
        await self._enforce_limit(
            _IDENTIFIER_DIMENSION,
            _normalize_identifier(identifier),
            tenant_id=tenant_id,
            limit=self._settings.account_rate_limit,
            window=self._settings.account_rate_window,
        )

        target = await self._org.reset_target(tenant_id, identifier)
        if not target.deliverable or target.user_id is None or not target.target:
            _LOGGER.info("找回密码未送达", tenant=tenant_code, found=target.found, deliverable=target.deliverable)
            return PasswordForgotResult(sent=True)

        await self._enforce_limit(
            _USER_DIMENSION,
            str(target.user_id),
            tenant_id=tenant_id,
            limit=self._settings.account_rate_limit,
            window=self._settings.account_rate_window,
        )
        token = secrets.token_urlsafe(32)
        await self._save_token(token, target, tenant=tenant_id)
        await self._send_token(token, target, tenant_code=tenant_code)
        _LOGGER.info("找回密码已发起", tenant=tenant_code, user_id=target.user_id, channel=target.channel)
        return PasswordForgotResult(sent=True)

    async def reset_password(
        self, token: str, new_password: str, *, tenant_id: str, tenant_code: str
    ) -> PasswordResetResult:
        """提交重置：一次性消费 token → 改密（强制过策略）→ 全部会话失效。

        Args:
            token: 重置令牌（单次有效）。
            new_password: 新口令明文（策略判定在 org 侧）。
            tenant_id: 租户主键（雪花 id 字符串；token 存储键 / org 调用 / 会话键依据）。
            tenant_code: 租户编码（展示）。

        Returns:
            PasswordResetResult: `reset=True`。

        Raises:
            PasswordResetTokenError: 令牌无效 / 过期 / 已用 / 账号已不存在（20005/400）。
            PasswordPolicyViolationError: 新密码不合规（30005）。
            PasswordReusedError: 命中历史密码（30006）。
            ServiceUnavailableError: org 不可用（10007/503）。
        """
        payload = await self._state.consume(token, tenant=tenant_id, namespace=PASSWORD_RESET_NAMESPACE)
        user_id, account = _parse_token_payload(payload)
        updated = await self._org.update_password(tenant_id, account, new_password)
        if not updated:
            raise PasswordResetTokenError("重置令牌无效或已过期")
        revoked = await self._sessions.revoke_user_sessions(user_id, tenant=tenant_id, reason=REASON_PASSWORD_RESET)
        _LOGGER.info("密码已重置", tenant=tenant_code, user_id=user_id, revoked_sessions=len(revoked))
        return PasswordResetResult(reset=True)

    async def _enforce_ip_limit(self, tenant_id: str, ip: str | None) -> None:
        """IP 维度限流（缺失 IP 跳过；先于验证码计数）。

        Args:
            tenant_id: 租户主键（雪花 id 字符串；限流键租户位）。
            ip: 客户端 IP（可选）。

        Raises:
            PasswordResetTooFrequentError: 超出配额（20006/429）。
        """
        if not ip:
            return
        await self._enforce_limit(
            _IP_DIMENSION,
            ip,
            tenant_id=tenant_id,
            limit=self._settings.ip_rate_limit,
            window=self._settings.ip_rate_window,
        )

    async def _enforce_captcha(self, captcha: CaptchaInput | None) -> None:
        """验证码：按场景策略强制，或请求携带时校验（不通过不消耗标识 / 用户配额）。

        Args:
            captcha: 请求携带的验证码凭证（可选）。

        Raises:
            CaptchaVerifyError: 策略强制但未携带（20101）。
            ParamError: 验证码形态非法（10001）。
            CaptchaVerifyError: 凭证校验不通过（20101）。
        """
        policy = await self._captcha.policy(_RESET_SCENE)
        if captcha is None:
            if policy.required:
                raise CaptchaVerifyError("需要验证码")
            return
        try:
            kind = CaptchaKind(captcha.kind)
        except ValueError as exc:
            raise ParamError(f"验证码形态非法：{captcha.kind}") from exc
        await self._captcha.require_credential(
            CaptchaCredential(
                captcha_id=captcha.captcha_id,
                kind=kind,
                code=captcha.code,
                trace=tuple(captcha.trace),
                scene=_RESET_SCENE,
            )
        )

    async def _enforce_limit(self, dimension: str, target: str, *, tenant_id: str, limit: int, window: int) -> None:
        """按维度限流（固定窗口计数；命中抛 20006）。

        Args:
            dimension: 限流维度名。
            target: 维度目标。
            tenant_id: 租户主键（雪花 id 字符串；限流键租户位）。
            limit: 窗口内上限。
            window: 窗口长度（秒）。

        Raises:
            PasswordResetTooFrequentError: 超出配额（20006/429）。
        """
        decision = await self._limiter.check(
            build_rate_limit_key(dimension=dimension, target=target, tenant=tenant_id),
            RateLimitRule(limit=limit, window=window),
        )
        if not decision.allowed:
            raise PasswordResetTooFrequentError("找回密码请求过于频繁，请稍后再试")

    async def _save_token(self, token: str, target: OrgResetTargetResult, *, tenant: str) -> None:
        """写入重置 token（流程状态存储；失败按服务不可用，不假报已发送）。

        Args:
            token: 重置令牌。
            target: 重置目标（载荷带用户 / 账号）。
            tenant: 租户主键（雪花 id 字符串；存储键租户位）。

        Raises:
            ServiceUnavailableError: 存储不可用（10007/503）。
        """
        payload: Mapping[str, object] = {
            "user_id": target.user_id,
            "account": target.account,
            "tenant_id": tenant,
        }
        try:
            await self._state.save(
                token,
                payload,
                tenant=tenant,
                ttl=self._settings.token_ttl_seconds,
                namespace=PASSWORD_RESET_NAMESPACE,
            )
        except Exception as exc:
            raise ServiceUnavailableError("重置令牌写入失败") from exc

    async def _send_token(self, token: str, target: OrgResetTargetResult, *, tenant_code: str) -> None:
        """经通知基座占位发送重置信息（渠道异常 / 未送达按服务不可用）。

        Args:
            token: 重置令牌（内容含令牌 / 重置链接；不回显响应）。
            target: 重置目标（通道与投递地址）。
            tenant_code: 租户编码（重置链接参数，对外）。

        Raises:
            ServiceUnavailableError: 通知渠道不可用或未送达（10007/503）。
        """
        message = self._build_message(token, target, tenant_code=tenant_code)
        try:
            result = await self._notifier.send(message)
        except Exception as exc:
            raise ServiceUnavailableError("重置通知发送失败") from exc
        if not result.delivered:
            raise ServiceUnavailableError("重置通知发送失败")

    def _build_message(self, token: str, target: OrgResetTargetResult, *, tenant_code: str) -> NotificationMessage:
        """构造通知消息（邮件 / 短信；内容已渲染，模板与真实渠道归阶段八）。

        Args:
            token: 重置令牌。
            target: 重置目标。
            tenant_code: 租户编码（重置链接参数，对外边界保持 code）。

        Returns:
            NotificationMessage: 通知消息。
        """
        minutes = max(1, self._settings.token_ttl_seconds // 60)
        if self._settings.reset_url:
            link = f"{self._settings.reset_url}?token={token}&tenant={tenant_code}"
            action = f"打开以下链接完成重置（每个链接仅可使用一次）：{link}"
        else:
            action = f"使用以下重置令牌完成重置（单次有效）：{token}"
        channel = NotifyChannel(target.channel)
        return NotificationMessage(
            channel=channel,
            recipient=target.target,
            title="BMS 密码重置" if channel is NotifyChannel.EMAIL else "",
            content=f"您正在找回账号（{target.account}）的密码，请在 {minutes} 分钟内{action}。",
            biz_type="password_reset",
            biz_id=str(target.user_id or ""),
        )


def _normalize_identifier(identifier: str) -> str:
    """标识归一化（限流键口径）：去首尾空白；含 `@` 的邮箱小写。

    Args:
        identifier: 原始标识。

    Returns:
        str: 归一化标识。
    """
    normalized = identifier.strip()
    return normalized.lower() if "@" in normalized else normalized


def _parse_token_payload(payload: Mapping[str, object] | None) -> tuple[int, str]:
    """解析并校验 token 载荷（缺失 / 已消费 / 过期 / 脏值统一按令牌无效）。

    Args:
        payload: 流程状态载荷。

    Returns:
        tuple[int, str]: (用户 ID, 登录账号)。

    Raises:
        PasswordResetTokenError: 载荷缺失或非法（20005/400）。
    """
    if payload is None:
        raise PasswordResetTokenError("重置令牌无效或已过期")
    user_id = payload.get("user_id")
    account = payload.get("account")
    if not isinstance(user_id, int) or not isinstance(account, str) or not account:
        raise PasswordResetTokenError("重置令牌无效或已过期")
    return user_id, account
