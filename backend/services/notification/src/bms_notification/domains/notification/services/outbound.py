"""外发调度：渠道过滤 / 免打扰 / 地址解析 / 渲染 / 日志 / 作业提交的唯一入口。

- 事务由调用方（路由工作单元 / 通知组消费 / 内部端点）负责；
- 渠道开关与免打扰只在这里判定一次；通知组把已读偏好传入，避免二次跨服务读取；
- 邮件正文放作业负载、日志不存正文；短信日志正文脱敏。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict
from bms_core.core.config import MailSettings, SmsSettings, get_settings
from bms_core.core.context import get_current_tenant_id
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseValueObject
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.i18n.base import get_default_locale
from bms_core.jobs.runner import JobRunner
from bms_core.jobs.spec import JobSubmission
from bms_core.notification.preference import (
    BaseNotificationPreferenceStore,
    NotificationPreference,
    default_notification_preference,
)
from bms_core.notification.preference_null import NullNotificationPreferenceStore
from bms_core.optionset.base import BaseOptionSetRegistry
from bms_notification.domains.notification.delivery_constants import (
    DELIVERY_ERROR_MAX_LENGTH,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_PENDING,
    DELIVERY_STATUS_SKIPPED,
    MAIL_JOB_TYPE,
    SMS_JOB_TYPE,
)
from bms_notification.domains.notification.models.mail import SysMailLog
from bms_notification.domains.notification.models.sms import SysSmsLog
from bms_notification.domains.notification.repositories.mail import MailRepository
from bms_notification.domains.notification.repositories.sms import SmsRepository
from bms_notification.domains.notification.services.mail import MailTemplateService
from bms_notification.domains.notification.services.recipient import RecipientInfo, RecipientResolver
from bms_notification.domains.notification.services.sms import SmsTemplateService

__all__ = [
    "CHANNEL_EMAIL",
    "CHANNEL_SMS",
    "DispatchOutcome",
    "DispatchRequest",
    "JobSubmitter",
    "OutboundDispatchService",
    "mask_sensitive",
]

CHANNEL_EMAIL = "email"
"""邮件渠道。"""

CHANNEL_SMS = "sms"
"""短信渠道。"""

_DIGITS = re.compile(r"\d{4,}")
"""连续 4 位及以上数字（验证码 / 令牌脱敏）。"""


def mask_sensitive(content: str | None) -> str | None:
    """短信正文脱敏（连续 4 位及以上数字替换为 `****`）。

    Args:
        content: 原始正文。

    Returns:
        str | None: 脱敏正文；None 原样返回。
    """
    if content is None:
        return None
    return _DIGITS.sub("****", content)


@dataclass(frozen=True)
class DispatchRequest(BaseValueObject):
    """一次外发请求（API / 内部端点 / 通知组共用）。"""

    channel: str
    """渠道（email / sms）。"""

    template_code: str | None = None
    """模板 code（邮件 raw 发送可空；短信必填）。"""

    params: ConcurrentStableFrozenDict[str, str] = field(default_factory=lambda: ConcurrentStableFrozenDict())
    """模板参数。"""

    user_id: int | None = None
    """收件用户主键。"""

    recipient: str | None = None
    """显式收件地址。"""

    locale: str | None = None
    """显式语言。"""

    transactional: bool = False
    """事务性消息（跳过渠道开关与免打扰）。"""

    title: str = ""
    """邮件 raw 主题 / 短信空。"""

    content: str = ""
    """邮件 raw 正文。"""

    html: bool = False
    """邮件正文是否 HTML（raw 发送）。"""

    idempotency_key: str | None = None
    """幂等键。"""

    record_skipped_when_disabled: bool = True
    """渠道关闭时是否落 skipped 日志（API 是；通知组否）。"""

    fail_on_missing_recipient: bool = True
    """地址缺失时是否抛参数错误（API 是；通知组否，落 failed）。"""


@dataclass(frozen=True)
class DispatchOutcome(BaseValueObject):
    """外发受理结果。"""

    log_id: int | None
    """发送记录主键；渠道关闭且不落日志时为 None。"""

    status: str
    """状态（pending / skipped / failed / filtered）。"""


class JobSubmitter(Protocol):
    """作业提交协议（生产走作业中心，测试注入替身）。"""

    async def submit(
        self,
        session: DbSession,
        *,
        job_type: str,
        payload: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> int:
        """提交作业并返回作业主键。

        Args:
            session: 当前租户库会话。
            job_type: 作业类型。
            payload: 作业负载。
            tenant_id: 租户主键。

        Returns:
            int: 作业主键。
        """
        ...


class DefaultJobSubmitter(BaseFrameworkObject):
    """作业中心提交器（懒建 `JobRunner`）。"""

    def __init__(self) -> None:
        """初始化（不在此处构建 runner，避免无作业路径也加载 worker 依赖）。"""
        self._runner: JobRunner | None = None

    async def submit(
        self,
        session: DbSession,
        *,
        job_type: str,
        payload: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> int:
        """提交作业。

        Args:
            session: 当前租户库会话。
            job_type: 作业类型。
            payload: 作业负载。
            tenant_id: 租户主键。

        Returns:
            int: 作业主键。
        """
        runner = self._get_runner()
        record = await runner.submit(
            session,
            JobSubmission(job_type=job_type, payload=payload),
            tenant_id=tenant_id,
        )
        return int(record.id)

    def _get_runner(self) -> JobRunner:
        """懒建作业提交器。

        Returns:
            JobRunner: 作业提交器。
        """
        if self._runner is None:
            from bms_notification.jobs import build_runner

            self._runner = build_runner()
        return self._runner


class OutboundDispatchService(BaseFrameworkObject):
    """外发调度服务（当前租户库会话）。"""

    def __init__(
        self,
        session: DbSession,
        *,
        preference: BaseNotificationPreferenceStore | None = None,
        recipient_resolver: RecipientResolver,
        option_sets: BaseOptionSetRegistry | None = None,
        mail_settings: MailSettings | None = None,
        sms_settings: SmsSettings | None = None,
        jobs: JobSubmitter | None = None,
        now: datetime | None = None,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            preference: 通知偏好读取（API / 内部入口由调度器加载）。
            recipient_resolver: 收件人解析器。
            option_sets: 选项集注册表（短信模板创建用；发送可空）。
            mail_settings: 邮件配置（缺省取全局）。
            sms_settings: 短信配置（缺省取全局）。
            jobs: 作业提交器（缺省作业中心）。
            now: 当前 UTC 时间（测试注入）。
        """
        settings = get_settings()
        self._session = session
        self._preference = preference or NullNotificationPreferenceStore()
        self._recipient = recipient_resolver
        self._mail_settings = mail_settings or settings.mail
        self._sms_settings = sms_settings or settings.sms
        self._jobs = jobs or DefaultJobSubmitter()
        self._now = now
        self._mail_templates = MailTemplateService(
            session, render_timeout_seconds=self._mail_settings.render_timeout_seconds
        )
        self._sms_templates = SmsTemplateService(
            session,
            option_sets=option_sets,
            sms_settings=self._sms_settings,
            render_timeout_seconds=self._mail_settings.render_timeout_seconds,
        )
        self._mail_logs = MailRepository(session)
        self._sms_logs = SmsRepository(session)

    async def dispatch(
        self,
        request: DispatchRequest,
        *,
        preference: NotificationPreference | None = None,
    ) -> DispatchOutcome:
        """受理一次外发请求（不发送，落日志 + 提交作业）。

        Args:
            request: 外发请求。
            preference: 已读偏好（通知组传入；None 时由调度器加载）。

        Returns:
            DispatchOutcome: 受理结果。

        Raises:
            ParamError: 收件地址缺失 / 短信缺模板 / 参数非法（10001）。
            ChannelConfigInvalidError: 渠道未配置（70305）。
            MailTemplateNotFoundError: 邮件模板不存在 / 停用（70301）。
            SmsTemplateUnavailableError: 短信模板不可用（70304）。
            TemplateRenderError: 渲染失败（70303）。
        """
        existing = await self._find_existing(request)
        if existing is not None:
            return existing
        pref = await self._resolve_preference(request, preference)
        now = self._now or datetime.now(UTC).replace(tzinfo=None)
        if not request.transactional and not pref.channel_enabled(request.channel):
            if not request.record_skipped_when_disabled:
                return DispatchOutcome(log_id=None, status="filtered")
            log_id = await self._create_skipped(request, reason="channel_disabled")
            return DispatchOutcome(log_id=log_id, status=DELIVERY_STATUS_SKIPPED)
        if not request.transactional and pref.in_quiet_hours(now):
            log_id = await self._create_skipped(request, reason="dnd")
            return DispatchOutcome(log_id=log_id, status=DELIVERY_STATUS_SKIPPED)
        info = await self._resolve_recipient(request)
        recipient = request.recipient or (info.email if request.channel == CHANNEL_EMAIL else info.phone)
        if not recipient:
            if request.fail_on_missing_recipient:
                raise ParamError("收件地址缺失（邮箱 / 手机号）")
            log_id = await self._create_failed(request, reason="收件地址缺失")
            return DispatchOutcome(log_id=log_id, status=DELIVERY_STATUS_FAILED)
        locale = request.locale or info.locale or get_default_locale()
        if request.channel == CHANNEL_EMAIL:
            return await self._dispatch_mail(request, recipient=recipient, locale=locale)
        return await self._dispatch_sms(request, recipient=recipient, locale=locale)

    async def record_failure(self, request: DispatchRequest, *, reason: str) -> DispatchOutcome:
        """记录一条 failed 日志（不发送；通知组消费用）。

        Args:
            request: 外发请求。
            reason: 失败原因。

        Returns:
            DispatchOutcome: 终态结果。
        """
        log_id = await self._create_failed(request, reason=reason)
        return DispatchOutcome(log_id=log_id, status=DELIVERY_STATUS_FAILED)

    async def _dispatch_mail(self, request: DispatchRequest, *, recipient: str, locale: str) -> DispatchOutcome:
        """渲染并落邮件日志 + 作业。"""
        if request.template_code:
            subject, content, _locale = await self._mail_templates.render_for_send(
                request.template_code, params=request.params, locale=locale
            )
            html = True
        else:
            subject = request.title.strip()
            content = request.content
            html = request.html
            if not subject:
                raise ParamError("邮件主题不得为空")
        log = SysMailLog(
            recipient=recipient,
            subject=subject,
            template_code=request.template_code,
            status=DELIVERY_STATUS_PENDING,
            locale=locale,
            user_id=request.user_id,
            idempotency_key=request.idempotency_key,
        )
        self._session.add(log)
        await self._session.flush()
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "log_id": str(int(log.id)),
                "kind": "mail",
                "recipient": recipient,
                "title": subject,
                "content": content,
                "html": html,
                "locale": locale,
                "template_code": request.template_code,
            }
        )
        job_id = await self._jobs.submit(
            self._session,
            job_type=MAIL_JOB_TYPE,
            payload=payload,
            tenant_id=_tenant_id_int(),
        )
        log.job_id = job_id
        await self._session.flush()
        return DispatchOutcome(log_id=int(log.id), status=DELIVERY_STATUS_PENDING)

    async def _dispatch_sms(self, request: DispatchRequest, *, recipient: str, locale: str) -> DispatchOutcome:
        """解析短信模板并落日志 + 作业（云短信必须模板化）。"""
        if not request.template_code:
            raise ParamError("短信发送必须提供 template_code")
        resolved = await self._sms_templates.resolve_for_send(request.template_code, params=request.params)
        log = SysSmsLog(
            recipient=recipient,
            channel=self._sms_templates.active_channel,
            template_code=request.template_code,
            scene=resolved.scene,
            content=mask_sensitive(resolved.content),
            status=DELIVERY_STATUS_PENDING,
            user_id=request.user_id,
            idempotency_key=request.idempotency_key,
        )
        self._session.add(log)
        await self._session.flush()
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "log_id": str(int(log.id)),
                "kind": "sms",
                "channel": self._sms_templates.active_channel,
                "recipient": recipient,
                "content": resolved.content,
                "locale": locale,
                "template_code": request.template_code,
                "provider_template_id": resolved.provider_template_id,
                "provider_param_keys": list(resolved.provider_param_keys),
                "params": dict(request.params),
            }
        )
        job_id = await self._jobs.submit(
            self._session,
            job_type=SMS_JOB_TYPE,
            payload=payload,
            tenant_id=_tenant_id_int(),
        )
        log.job_id = job_id
        await self._session.flush()
        return DispatchOutcome(log_id=int(log.id), status=DELIVERY_STATUS_PENDING)

    async def _create_skipped(self, request: DispatchRequest, *, reason: str) -> int:
        """落 skipped 日志（渠道关闭 / 免打扰），不提交作业。"""
        return await self._create_terminal(request, status=DELIVERY_STATUS_SKIPPED, reason=reason)

    async def _create_failed(self, request: DispatchRequest, *, reason: str) -> int:
        """落 failed 日志（地址缺失等），不提交作业。"""
        return await self._create_terminal(request, status=DELIVERY_STATUS_FAILED, reason=reason)

    async def _create_terminal(self, request: DispatchRequest, *, status: str, reason: str) -> int:
        """落终态日志（skipped / failed）。"""
        error = reason[:DELIVERY_ERROR_MAX_LENGTH]
        if request.channel == CHANNEL_EMAIL:
            log = SysMailLog(
                recipient=request.recipient,
                template_code=request.template_code,
                status=status,
                error_msg=error,
                locale=request.locale,
                user_id=request.user_id,
                idempotency_key=request.idempotency_key,
            )
        else:
            log = SysSmsLog(
                recipient=request.recipient,
                channel=self._sms_templates.active_channel,
                template_code=request.template_code,
                status=status,
                error_msg=error,
                user_id=request.user_id,
                idempotency_key=request.idempotency_key,
            )
        self._session.add(log)
        await self._session.flush()
        return int(log.id)

    async def _find_existing(self, request: DispatchRequest) -> DispatchOutcome | None:
        """按幂等键返回既有记录。"""
        if not request.idempotency_key:
            return None
        if request.channel == CHANNEL_EMAIL:
            row = await self._mail_logs.get_log_by_idempotency_key(request.idempotency_key)
        else:
            row = await self._sms_logs.get_log_by_idempotency_key(request.idempotency_key)
        if row is None:
            return None
        return DispatchOutcome(log_id=int(row.id), status=row.status)

    async def _resolve_preference(
        self, request: DispatchRequest, preference: NotificationPreference | None
    ) -> NotificationPreference:
        """取偏好：已传入优先；无用户或事务性发送用默认全开。"""
        if preference is not None:
            return preference
        if request.transactional or request.user_id is None:
            return default_notification_preference()
        return await self._preference.load(request.user_id)

    async def _resolve_recipient(self, request: DispatchRequest) -> RecipientInfo:
        """解析收件人（显式地址时不需要用户信息）。"""
        if request.recipient:
            return RecipientInfo(locale=request.locale)
        if request.user_id is None:
            return RecipientInfo()
        return await self._recipient.resolve(request.user_id)


def _tenant_id_int() -> int | None:
    """当前租户主键（字符串 → int；缺失按 None）。"""
    raw = get_current_tenant_id()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
