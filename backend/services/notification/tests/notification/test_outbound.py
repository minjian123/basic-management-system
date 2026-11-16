"""外发调度：渠道过滤 / 免打扰 / 事务性 / 地址 / 幂等 / 日志与作业。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import AliyunSmsSettings, MailSettings, SmsSettings, TencentSmsSettings
from bms_core.core.exceptions import ParamError
from bms_core.notification.preference import BaseNotificationPreferenceStore, NotificationPreference
from bms_core.testing.transaction import rollback_session
from bms_notification.domains.notification.models.mail import SysMailLog
from bms_notification.domains.notification.models.sms import SysSmsLog
from bms_notification.domains.notification.services.outbound import (
    CHANNEL_EMAIL,
    CHANNEL_SMS,
    DispatchRequest,
    OutboundDispatchService,
)
from bms_notification.domains.notification.services.recipient import RecipientInfo, RecipientResolver

pytestmark = pytest.mark.kiwi_id(2519)


class _Preference:
    def __init__(self, pref: NotificationPreference | None = None) -> None:
        self.pref = pref or NotificationPreference()

    async def load(self, user_id: int) -> NotificationPreference:
        del user_id
        return self.pref


class _Resolver:
    def __init__(self, info: RecipientInfo | None = None) -> None:
        self.info = info or RecipientInfo(email="a@b.c", phone="13800000000", locale="zh-CN")

    async def resolve(self, user_id: int) -> RecipientInfo:
        del user_id
        return self.info


class _Jobs:
    def __init__(self) -> None:
        self.calls: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()

    async def submit(
        self,
        session: object,
        *,
        job_type: str,
        payload: ConcurrentStableDict[str, object],
        tenant_id: int | None,
    ) -> int:
        del session, tenant_id
        self.calls.add((job_type, payload))
        return len(self.calls)


def _service(session: object, *, pref: NotificationPreference | None = None, jobs: _Jobs | None = None):
    settings = SmsSettings(
        channel="aliyun",
        aliyun=AliyunSmsSettings(access_key_id="ak", access_key_secret="sk", sign_name="BMS"),
        tencent=TencentSmsSettings(secret_id="id", secret_key="key", sdk_app_id="app", sign_name="BMS"),
    )
    return OutboundDispatchService(
        session,  # pyright: ignore[reportArgumentType]
        preference=cast("BaseNotificationPreferenceStore", _Preference(pref)),
        recipient_resolver=cast("RecipientResolver", _Resolver()),
        mail_settings=MailSettings(render_timeout_seconds=3),
        sms_settings=settings,
        jobs=jobs or _Jobs(),  # pyright: ignore[reportArgumentType]
        now=datetime(2026, 1, 1, 12, 0, tzinfo=UTC).replace(tzinfo=None),
    )


def _request(**overrides: object) -> DispatchRequest:
    values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "channel": CHANNEL_EMAIL,
            "template_code": "approval_todo",
            "params": ConcurrentStableFrozenDict({"title": "审批", "content": "内容"}),
            "recipient": "a@b.c",
            "user_id": 123,
            "transactional": False,
        }
    )
    values.update(overrides)
    return DispatchRequest(**values)  # pyright: ignore[reportArgumentType]


async def test_email_dispatch_creates_log_and_job(shared_tenant_engine: AsyncEngine) -> None:
    """邮件受理：pending 日志 + 作业负载含渲染正文。"""
    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        outcome = await _service(session, jobs=jobs).dispatch(_request())
        assert outcome.status == "pending"
        log = (await session.execute(select(SysMailLog))).scalars().one()
        assert log.status == "pending"
        assert log.subject and "审批" in log.subject
        assert jobs.calls[0][0] == "notification.mail.send"
        assert "审批" in str(jobs.calls[0][1]["content"])


async def test_dnd_and_transactional(shared_tenant_engine: AsyncEngine) -> None:
    """免打扰落 skipped；事务性绕过。"""
    pref = NotificationPreference(dnd_enabled=True, dnd_start="00:00", dnd_end="23:59", timezone="UTC")
    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        outcome = await _service(session, pref=pref, jobs=jobs).dispatch(_request())
        assert outcome.status == "skipped"
        log = (await session.execute(select(SysMailLog))).scalars().one()
        assert log.error_msg == "dnd"
        assert jobs.calls == []

    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        outcome = await _service(session, pref=pref, jobs=jobs).dispatch(_request(transactional=True))
        assert outcome.status == "pending"
        assert len(jobs.calls) == 1


async def test_channel_disabled(shared_tenant_engine: AsyncEngine) -> None:
    """渠道关闭：API 落 skipped；通知组不落日志。"""
    pref = NotificationPreference(channels=ConcurrentStableFrozenDict({"inbox": True, "email": False, "sms": True}))
    async with rollback_session(shared_tenant_engine) as session:
        outcome = await _service(session, pref=pref).dispatch(_request())
        assert outcome.status == "skipped"
        assert (await session.execute(select(SysMailLog))).scalars().one()

    async with rollback_session(shared_tenant_engine) as session:
        outcome = await _service(session, pref=pref).dispatch(_request(record_skipped_when_disabled=False))
        assert outcome.status == "filtered"
        assert (await session.execute(select(SysMailLog))).scalars().all() == []


async def test_missing_recipient_and_idempotency(shared_tenant_engine: AsyncEngine) -> None:
    """地址缺失：API 抛错 / 通知组落 failed；幂等键返回同记录。"""
    async with rollback_session(shared_tenant_engine) as session:
        with pytest.raises(ParamError):
            await _service(session).dispatch(_request(recipient=None, user_id=None))
        outcome = await _service(session).dispatch(
            _request(
                recipient=None,
                user_id=None,
                fail_on_missing_recipient=False,
            )
        )
        assert outcome.status == "failed"
        log = (await session.execute(select(SysMailLog))).scalars().one()
        assert log.status == "failed"

    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        service = _service(session, jobs=jobs)
        first = await service.dispatch(_request(idempotency_key="k-1"))
        second = await service.dispatch(_request(idempotency_key="k-1"))
        assert first.log_id == second.log_id
        assert len(jobs.calls) == 1


async def test_sms_template_required_and_mask(shared_tenant_engine: AsyncEngine) -> None:
    """短信无模板抛错；内置验证码模板落脱敏正文。"""
    async with rollback_session(shared_tenant_engine) as session:
        with pytest.raises(ParamError):
            await _service(session).dispatch(_request(channel=CHANNEL_SMS, template_code=None, recipient="13800000000"))

    async with rollback_session(shared_tenant_engine) as session:
        jobs = _Jobs()
        settings = SmsSettings(
            channel="aliyun",
            aliyun=AliyunSmsSettings(
                access_key_id="ak", access_key_secret="sk", sign_name="BMS", captcha_template_id="SMS_1"
            ),
        )
        service = OutboundDispatchService(
            session,
            preference=cast("BaseNotificationPreferenceStore", _Preference()),
            recipient_resolver=cast("RecipientResolver", _Resolver()),
            mail_settings=MailSettings(render_timeout_seconds=3),
            sms_settings=settings,
            jobs=jobs,
            now=datetime(2026, 1, 1, 12, 0),
        )
        outcome = await service.dispatch(
            _request(
                channel=CHANNEL_SMS,
                template_code="sms_captcha",
                params=ConcurrentStableFrozenDict({"code": "123456", "minutes": "5"}),
                recipient="13800000000",
            )
        )
        assert outcome.status == "pending"
        log = (await session.execute(select(SysSmsLog))).scalars().one()
        assert "123456" not in (log.content or "")
        assert "****" in (log.content or "")
        assert jobs.calls[0][1]["provider_template_id"] == "SMS_1"
