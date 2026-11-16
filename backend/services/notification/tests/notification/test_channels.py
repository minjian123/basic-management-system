"""真实通道适配：SMTP / 阿里云 / 腾讯云（假传输，不连外网）。"""

# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
from __future__ import annotations

import json
from email.message import EmailMessage

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import AliyunSmsSettings, MailSettings, TencentSmsSettings
from bms_notification.domains.notification.channels.aliyun import AliyunSmsChannel
from bms_notification.domains.notification.channels.smtp import SmtpMailChannel
from bms_notification.domains.notification.channels.tencent import TencentSmsChannel

pytestmark = pytest.mark.kiwi_id(2519)


async def test_smtp_success_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """SMTP 配置完整时发送；缺配置直接失败。"""
    sent: ConcurrentStableList[tuple[EmailMessage, ConcurrentStableDict[str, object]]] = ConcurrentStableList()

    async def _send(message: EmailMessage, **kwargs: object) -> None:
        sent.add((message, ConcurrentStableDict(kwargs)))

    import bms_notification.domains.notification.channels.smtp as module

    monkeypatch.setattr(module.aiosmtplib, "send", _send)
    channel = SmtpMailChannel(
        MailSettings(smtp_host="smtp.local", smtp_from="bms@local", smtp_username="u", smtp_password="p")
    )
    result = await channel.send(recipient="a@b.c", subject="主题", content="正文", html=False)
    assert result.delivered is True
    assert len(sent) == 1
    message = sent[0][0]
    assert message["Subject"] == "主题"  # type: ignore[index]

    missing = await SmtpMailChannel(MailSettings()).send(recipient="a@b.c", subject="主题", content="正文", html=False)
    assert missing.delivered is False
    assert missing.retryable is False


async def test_smtp_failure_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    """认证失败不可重试；连接失败可重试。"""
    import bms_notification.domains.notification.channels.smtp as module

    async def _auth(*args: object, **kwargs: object) -> None:
        raise module.aiosmtplib.SMTPAuthenticationError(535, "bad")

    monkeypatch.setattr(module.aiosmtplib, "send", _auth)
    channel = SmtpMailChannel(MailSettings(smtp_host="h", smtp_from="f"))
    result = await channel.send(recipient="a@b.c", subject="s", content="c", html=False)
    assert result.delivered is False
    assert result.retryable is False

    async def _down(*args: object, **kwargs: object) -> None:
        raise OSError("down")

    monkeypatch.setattr(module.aiosmtplib, "send", _down)
    result = await channel.send(recipient="a@b.c", subject="s", content="c", html=False)
    assert result.delivered is False
    assert result.retryable is True


async def test_aliyun_success_and_error() -> None:
    """阿里云签名请求与错误码分类。"""
    seen: ConcurrentStableList[httpx.Request] = ConcurrentStableList()

    def _ok(request: httpx.Request) -> httpx.Response:
        seen.add(request)
        return httpx.Response(200, json={"Code": "OK", "BizId": "biz-1"})

    settings = AliyunSmsSettings(
        access_key_id="ak", access_key_secret="sk", sign_name="BMS", captcha_template_id="SMS_1"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ok)) as client:
        channel = AliyunSmsChannel(settings, client=client)
        result = await channel.send(
            phone="13800000000",
            provider_template_id="SMS_1",
            params=ConcurrentStableDict({"code": "123456"}),
            param_keys=ConcurrentStableList(("code",)),
        )
    assert result.delivered is True
    assert result.provider_message_id == "biz-1"
    assert "Signature=" in seen[0].content.decode()

    def _throttle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Code": "isv.BUSINESS_LIMIT_CONTROL", "Message": "limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_throttle)) as client:
        result = await AliyunSmsChannel(settings, client=client).send(
            phone="13800000000",
            provider_template_id="SMS_1",
            params=ConcurrentStableDict({"code": "1"}),
            param_keys=ConcurrentStableList(("code",)),
        )
    assert result.delivered is False
    assert result.retryable is True


async def test_tencent_success_and_error() -> None:
    """腾讯云 TC3 签名请求与错误码分类。"""
    seen: ConcurrentStableList[httpx.Request] = ConcurrentStableList()

    def _ok(request: httpx.Request) -> httpx.Response:
        seen.add(request)
        return httpx.Response(
            200, json={"Response": {"SendStatusSet": [{"Code": "Ok", "SerialNo": "serial-1"}], "RequestId": "r"}}
        )

    settings = TencentSmsSettings(secret_id="id", secret_key="key", sdk_app_id="app", sign_name="BMS")
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ok)) as client:
        result = await TencentSmsChannel(settings, client=client).send(
            phone="13800000000",
            provider_template_id="1001",
            params=ConcurrentStableDict({"code": "123456"}),
            param_keys=ConcurrentStableList(("code",)),
        )
    assert result.delivered is True
    assert result.provider_message_id == "serial-1"
    assert seen[0].headers["Authorization"].startswith("TC3-HMAC-SHA256")
    body = json.loads(seen[0].content)
    assert body["PhoneNumberSet"] == ["+8613800000000"]

    def _limit(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Response": {"Error": {"Code": "RequestLimitExceeded", "Message": "limit"}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_limit)) as client:
        result = await TencentSmsChannel(settings, client=client).send(
            phone="13800000000",
            provider_template_id="1001",
            params=ConcurrentStableDict({"code": "1"}),
            param_keys=ConcurrentStableList(("code",)),
        )
    assert result.delivered is False
    assert result.retryable is True
