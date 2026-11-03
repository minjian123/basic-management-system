"""登录审计记录器（identity · 认证域）：成功 / 失败统一写登录日志事件（06_01）。

- 失败原因映射与认证域异常一一对应（限流 / 验证码 / 锁定 / 停用 / 凭据 / 后端不可用）；
- 经 `AuditEventEmitter` 写本服务平台库发件箱（失败只告警，不影响登录结果）；
- 密码本身不进入载荷；`username` 明文记录（设计允许）。
"""

from __future__ import annotations

from bms_core.audit.emit import AuditEventEmitter
from bms_core.audit.events import build_login_event
from bms_core.core.config import Settings
from bms_core.core.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    CaptchaVerifyError,
    LoginFailedError,
    RateLimitError,
    ServiceUnavailableError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory

__all__ = ["FAIL_REASON_ACCOUNT_DISABLED", "LoginAuditRecorder", "classify_login_error"]

FAIL_REASON_RATE_LIMITED = "rate_limited"
FAIL_REASON_CAPTCHA_INVALID = "captcha_invalid"
FAIL_REASON_ACCOUNT_LOCKED = "account_locked"
FAIL_REASON_ACCOUNT_DISABLED = "account_disabled"
FAIL_REASON_BAD_CREDENTIALS = "bad_credentials"
FAIL_REASON_BACKEND_UNAVAILABLE = "backend_unavailable"
FAIL_REASON_INTERNAL = "internal_error"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"


def classify_login_error(exc: BaseException) -> str:
    """把登录异常映射为失败原因（`fail_reason`）。

    Args:
        exc: 登录链路抛出的异常。

    Returns:
        str: 失败原因（枚举值见模块常量）。
    """
    if isinstance(exc, RateLimitError):
        return FAIL_REASON_RATE_LIMITED
    if isinstance(exc, CaptchaVerifyError):
        return FAIL_REASON_CAPTCHA_INVALID
    if isinstance(exc, AccountLockedError):
        return FAIL_REASON_ACCOUNT_LOCKED
    if isinstance(exc, AccountDisabledError):
        return FAIL_REASON_ACCOUNT_DISABLED
    if isinstance(exc, LoginFailedError):
        return FAIL_REASON_BAD_CREDENTIALS
    if isinstance(exc, ServiceUnavailableError):
        return FAIL_REASON_BACKEND_UNAVAILABLE
    return FAIL_REASON_INTERNAL


class LoginAuditRecorder(BaseFrameworkObject):
    """登录审计记录器（应用级依赖 + 短会话发件箱）。"""

    def __init__(self, *, registry: EngineRegistry, session_factory: SessionFactory, settings: Settings) -> None:
        """初始化。

        Args:
            registry: 应用级引擎注册表。
            session_factory: 会话工厂。
            settings: 应用配置（发件箱实现 / 审计参数）。
        """
        self._emitter = AuditEventEmitter(
            registry=registry,
            session_factory=session_factory,
            settings=settings,
        )

    async def record(
        self,
        *,
        username: str,
        tenant_id: str | None,
        user_id: int | None,
        ip: str | None,
        user_agent: str | None,
        status: str,
        fail_reason: str | None = None,
        trace_id: str | None = None,
    ) -> bool:
        """写一条登录审计事件。

        Args:
            username: 登录名。
            tenant_id: 租户主键（字符串）。
            user_id: 命中用户主键（失败可为空）。
            ip: 客户端 IP。
            user_agent: User-Agent。
            status: `success` / `failed`。
            fail_reason: 失败原因（成功为空）。
            trace_id: 链路 id。

        Returns:
            bool: 写入成功 True（失败只告警）。
        """
        event = build_login_event(
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            ip=ip,
            user_agent=user_agent,
            status=status,
            fail_reason=fail_reason,
            trace_id=trace_id,
        )
        return await self._emitter.emit(event)
