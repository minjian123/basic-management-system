"""发送作业：成功 / 失败重试 / 幂等 / 负载非法。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.jobs.base import JobContext
from bms_core.testing.transaction import write_session
from bms_notification.domains.notification.channels.base import BaseMailChannel, BaseSmsChannel, ChannelResult
from bms_notification.domains.notification.models.mail import SysMailLog
from bms_notification.domains.notification.models.sms import SysSmsLog
from bms_notification.domains.notification.services.mail_jobs import MailSendJob
from bms_notification.domains.notification.services.sms_jobs import SmsSendJob

pytestmark = pytest.mark.kiwi_id(2519)


class _MailChannel:
    def __init__(self, result: ChannelResult) -> None:
        self.result = result
        self.sent: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()

    async def send(self, *, recipient: str, subject: str, content: str, html: bool) -> ChannelResult:
        del html
        self.sent.add((recipient, subject))
        return self.result


class _SmsChannel:
    def __init__(self, result: ChannelResult) -> None:
        self.result = result
        self.sent: ConcurrentStableList[str] = ConcurrentStableList()

    async def send(
        self,
        *,
        phone: str,
        provider_template_id: str,
        params: object,
        param_keys: ConcurrentStableList[str],
    ) -> ChannelResult:
        del provider_template_id, params, param_keys
        self.sent.add(phone)
        return self.result


def _context(
    session: object,
    *,
    payload: ConcurrentStableDict[str, object],
    attempt: int = 1,
    max_attempts: int = 3,
) -> JobContext:
    @asynccontextmanager
    async def _open() -> AsyncGenerator[object]:
        yield session

    return JobContext(
        job_id=1,
        job_type="notification.mail.send",
        service_key="notification",
        db_key="tenant_demo",
        payload=ConcurrentStableDict(payload),
        attempt=attempt,
        max_attempts=max_attempts,
        open_session=lambda: _open(),
    )


def _mail_payload(log_id: int) -> ConcurrentStableDict[str, object]:
    return ConcurrentStableDict(
        {
            "log_id": str(log_id),
            "recipient": "a@b.c",
            "title": "主题",
            "content": "正文",
            "html": True,
        }
    )


def _sms_payload(log_id: int) -> ConcurrentStableDict[str, object]:
    return ConcurrentStableDict(
        {
            "log_id": str(log_id),
            "channel": "aliyun",
            "recipient": "13800000000",
            "provider_template_id": "SMS_1",
            "provider_param_keys": ["code"],
            "params": {"code": "123456"},
        }
    )


async def test_mail_job_success_and_idempotent(shared_tenant_engine: AsyncEngine) -> None:
    """成功回写 success；再次执行不重复发送。"""
    async with write_session(shared_tenant_engine) as session:
        log = SysMailLog(recipient="a@b.c", subject="主题", status="pending")
        session.add(log)
        await session.flush()
        channel = _MailChannel(ChannelResult(delivered=True, provider_message_id="m1"))
        job = MailSendJob(channel=cast("BaseMailChannel", channel))
        result = await job.run(_context(session, payload=_mail_payload(int(log.id))))
        assert result.status == "succeeded"
        await session.refresh(log)
        assert log.status == "success"
        assert log.attempts == 1
        assert log.sent_at is not None

        again = await job.run(_context(session, payload=_mail_payload(int(log.id))))
        assert again.status == "succeeded"
        assert channel.sent == [("a@b.c", "主题")]


async def test_mail_job_failure_retryable(shared_tenant_engine: AsyncEngine) -> None:
    """失败回写 failed；可重试由作业中心重试。"""
    async with write_session(shared_tenant_engine) as session:
        log = SysMailLog(recipient="a@b.c", subject="主题", status="pending")
        session.add(log)
        await session.flush()
        channel = _MailChannel(ChannelResult(delivered=False, error="smtp down", retryable=True))
        result = await MailSendJob(channel=cast("BaseMailChannel", channel)).run(
            _context(session, payload=_mail_payload(int(log.id)))
        )
        assert result.status == "failed"
        assert result.retryable is True
        await session.refresh(log)
        assert log.status == "failed"
        assert log.error_msg == "smtp down"


async def test_mail_job_bad_payload(shared_tenant_engine: AsyncEngine) -> None:
    """负载非法 / 记录不存在按不可重试失败。"""
    async with write_session(shared_tenant_engine) as session:
        result = await MailSendJob(channel=cast("BaseMailChannel", _MailChannel(ChannelResult(delivered=True)))).run(
            _context(session, payload=ConcurrentStableDict({"log_id": "x"}))
        )
        assert result.status == "failed"
        assert result.retryable is False


async def test_sms_job_success_and_failure(shared_tenant_engine: AsyncEngine) -> None:
    """短信成功 / 失败 / 记录不存在。"""
    async with write_session(shared_tenant_engine) as session:
        log = SysSmsLog(recipient="13800000000", channel="aliyun", status="pending", content="****")
        session.add(log)
        await session.flush()
        channel = _SmsChannel(ChannelResult(delivered=True, provider_message_id="s1"))
        result = await SmsSendJob(channel=cast("BaseSmsChannel", channel)).run(
            _context(session, payload=_sms_payload(int(log.id)))
        )
        assert result.status == "succeeded"
        await session.refresh(log)
        assert log.status == "success"
        assert channel.sent == ["13800000000"]

    async with write_session(shared_tenant_engine) as session:
        log = SysSmsLog(recipient="13800000000", channel="aliyun", status="pending", content="****")
        session.add(log)
        await session.flush()
        channel = _SmsChannel(ChannelResult(delivered=False, error="bad template", retryable=False))
        result = await SmsSendJob(channel=cast("BaseSmsChannel", channel)).run(
            _context(session, payload=_sms_payload(int(log.id)))
        )
        assert result.status == "failed"
        assert result.retryable is False
        await session.refresh(log)
        assert log.status == "failed"

    async with write_session(shared_tenant_engine) as session:
        result = await SmsSendJob(channel=cast("BaseSmsChannel", _SmsChannel(ChannelResult(delivered=True)))).run(
            _context(session, payload=_sms_payload(999999))
        )
        assert result.status == "failed"
        assert result.retryable is False
