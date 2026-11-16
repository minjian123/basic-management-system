"""阿里云短信通道（Dysmsapi RPC 签名，httpx 直连）。

- 只发送厂商已审核模板（`TemplateCode` + `TemplateParam`）；
- 签名：HMAC-SHA1（RPC 签名），参数名与模板变量名一致；
- 失败按厂商错误码分类可重试 / 不可重试。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import AliyunSmsSettings
from bms_core.core.logging import get_logger
from bms_notification.domains.notification.channels.base import BaseSmsChannel, ChannelResult

__all__ = ["AliyunSmsChannel"]

_LOGGER = get_logger("bms")

_RETRYABLE_CODES = frozenset(
    {
        "isv.BUSINESS_LIMIT_CONTROL",
        "isv.SYSTEM_ERROR",
        "isp.SYSTEM_ERROR",
        "Throttling",
        "Throttling.User",
        "ServiceUnavailable",
        "InternalError",
    }
)
"""可重试的阿里云错误码（限流 / 系统错误 / 服务不可用）。"""


def _percent_encode(value: str) -> str:
    """阿里云 RPC 规范 percent encode。"""
    return quote(value, safe="~")


class AliyunSmsChannel(BaseSmsChannel):
    """阿里云短信通道。"""

    def __init__(self, settings: AliyunSmsSettings, *, client: httpx.AsyncClient | None = None) -> None:
        """初始化。

        Args:
            settings: 阿里云短信配置。
            client: HTTP 客户端（测试注入 mock transport；None 每次新建）。
        """
        self._settings = settings
        self._client = client

    async def send(
        self,
        *,
        phone: str,
        provider_template_id: str,
        params: ConcurrentStableDict[str, str],
        param_keys: ConcurrentStableList[str],
    ) -> ChannelResult:
        """发送一条模板短信。

        Args:
            phone: 手机号。
            provider_template_id: 厂商模板 ID。
            params: 参数键值。
            param_keys: 参数顺序（阿里云按键名，顺序不敏感）。

        Returns:
            ChannelResult: 发送结果。
        """
        settings = self._settings
        if not settings.access_key_id or not settings.access_key_secret or not settings.sign_name:
            return ChannelResult(delivered=False, error="阿里云短信未配置（AK / 签名）", retryable=False)
        template_params = {key: str(params.get(key, "")) for key in param_keys}
        form: ConcurrentStableDict[str, str] = ConcurrentStableDict(
            {
                "AccessKeyId": settings.access_key_id,
                "Action": "SendSms",
                "Format": "JSON",
                "PhoneNumbers": _normalize_phone(phone),
                "RegionId": settings.region_id,
                "SignName": settings.sign_name,
                "SignatureMethod": "HMAC-SHA1",
                "SignatureNonce": uuid.uuid4().hex,
                "SignatureVersion": "1.0",
                "TemplateCode": provider_template_id,
                "TemplateParam": json.dumps(template_params, ensure_ascii=False, separators=(",", ":")),
                "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Version": "2017-05-25",
            }
        )
        form["Signature"] = _sign(form, secret=settings.access_key_secret)
        try:
            if self._client is not None:
                response = await self._client.post(settings.endpoint, data=form)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(settings.endpoint, data=form)
        except (httpx.HTTPError, OSError) as exc:
            _LOGGER.warning("阿里云短信请求失败", phone=phone, error=str(exc))
            return ChannelResult(delivered=False, error=f"阿里云短信请求失败：{exc}", retryable=True)
        if response.status_code >= 500:
            return ChannelResult(
                delivered=False, error=f"阿里云短信服务不可用（HTTP {response.status_code}）", retryable=True
            )
        try:
            payload = cast("object", response.json())
        except ValueError:
            return ChannelResult(delivered=False, error="阿里云短信响应非 JSON", retryable=True)
        if not isinstance(payload, dict):
            return ChannelResult(delivered=False, error="阿里云短信响应非法", retryable=True)
        data = cast("dict[str, object]", payload)
        code = str(data.get("Code") or "")
        if code == "OK":
            return ChannelResult(delivered=True, provider_message_id=str(data.get("BizId") or ""))
        message = str(data.get("Message") or "")
        _LOGGER.warning("阿里云短信发送失败", phone=phone, code=code, message=message)
        return ChannelResult(
            delivered=False,
            error=f"阿里云短信返回 {code}：{message}",
            retryable=code in _RETRYABLE_CODES,
        )


def _sign(form: ConcurrentStableDict[str, str], *, secret: str) -> str:
    """计算 RPC 签名（HMAC-SHA1）。"""
    canonical = "&".join(f"{_percent_encode(key)}={_percent_encode(str(form[key]))}" for key in sorted(form))
    string_to_sign = f"POST&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(f"{secret}&".encode(), string_to_sign.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _normalize_phone(phone: str) -> str:
    """阿里云手机号归一（去空格；去 `+86` 前缀）。"""
    value = phone.strip().replace(" ", "")
    if value.startswith("+86"):
        return value[3:]
    return value
