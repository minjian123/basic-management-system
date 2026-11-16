"""邮件 / 短信路由共用依赖与工具（语言解析、外发调度装配）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Query

from bms_core.api.deps import get_service_client, get_uow
from bms_core.core.config import get_settings
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.i18n.base import get_default_locale
from bms_core.notification.preference import BaseNotificationPreferenceStore, get_notification_preference_store
from bms_core.optionset.base import BaseOptionSetRegistry, get_option_set_registry
from bms_core.servicecall.base import BaseServiceClient
from bms_notification.domains.notification.services.outbound import (
    DefaultJobSubmitter,
    JobSubmitter,
    OutboundDispatchService,
)
from bms_notification.domains.notification.services.recipient import RecipientResolver

__all__ = [
    "AcceptLanguage",
    "IdempotencyKey",
    "LocaleQuery",
    "OutboundDep",
    "get_job_submitter",
    "get_outbound_dispatch_service",
    "get_recipient_resolver",
    "resolve_locale",
]

LocaleQuery = Annotated[str | None, Query(description="语言标识（缺省按 Accept-Language）")]
AcceptLanguage = Annotated[str | None, Header(alias="Accept-Language")]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]

_SUBMITTER: JobSubmitter = DefaultJobSubmitter()
"""进程级作业提交器（懒建 runner；测试可依赖覆盖）。"""


def resolve_locale(locale: str | None, accept_language: str | None) -> str:
    """解析请求语言：显式参数 → Accept-Language 主语言 → 系统默认语言。

    Args:
        locale: 显式语言。
        accept_language: 请求头。

    Returns:
        str: 生效语言。
    """
    if locale and locale.strip():
        return locale.strip()
    if accept_language:
        primary = accept_language.split(",", 1)[0].split(";", 1)[0].strip()
        if primary:
            return primary
    return get_default_locale()


def get_job_submitter() -> JobSubmitter:
    """取作业提交器（测试可覆盖）。

    Returns:
        JobSubmitter: 作业提交器。
    """
    return _SUBMITTER


def get_recipient_resolver(
    client: Annotated[BaseServiceClient, Depends(get_service_client)],
) -> RecipientResolver:
    """构造收件人解析器。

    Args:
        client: 服务间调用客户端。

    Returns:
        RecipientResolver: 收件人解析器。
    """
    return RecipientResolver(client)


def get_outbound_dispatch_service(
    uow: Annotated[DbUnitOfWork, Depends(get_uow)],
    preference: Annotated[BaseNotificationPreferenceStore, Depends(get_notification_preference_store)],
    recipient: Annotated[RecipientResolver, Depends(get_recipient_resolver)],
    registry: Annotated[BaseOptionSetRegistry, Depends(get_option_set_registry)],
    jobs: Annotated[JobSubmitter, Depends(get_job_submitter)],
) -> OutboundDispatchService:
    """构造外发调度服务（当前请求事务）。

    Args:
        uow: 请求级工作单元。
        preference: 通知偏好读取。
        recipient: 收件人解析器。
        registry: 选项集注册表。
        jobs: 作业提交器。

    Returns:
        OutboundDispatchService: 外发调度服务。
    """
    settings = get_settings()
    return OutboundDispatchService(
        uow.session,
        preference=preference,
        recipient_resolver=recipient,
        option_sets=registry,
        mail_settings=settings.mail,
        sms_settings=settings.sms,
        jobs=jobs,
    )


OutboundDep = Annotated[OutboundDispatchService, Depends(get_outbound_dispatch_service)]
