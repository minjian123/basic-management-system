"""腾讯云短信通道（TC3-HMAC-SHA256 签名，httpx 直连）。

- 只发送厂商已审核模板（`TemplateId` + `TemplateParamSet`）；
- 参数按 `param_keys` 顺序转数组；手机号归一为 `+86` 前缀；
- 失败按厂商错误码分类可重试 / 不可重试。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlparse

import httpx

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import TencentSmsSettings
from bms_core.core.logging import get_logger
from bms_notification.domains.notification.channels.base import BaseSmsChannel, ChannelResult

__all__ = ["TencentSmsChannel"]

_LOGGER = get_logger("bms")

_RETRYABLE_CODES = frozenset(
    {
        "RequestLimitExceeded",
        "LimitExceeded",
        "InternalError",
        "FailedOperation.ServiceUnavailable",
        "FailedOperation.SystemBusy",
    }
)
"""可重试的腾讯云错误码（限流 / 内部错误 / 服务不可用）。"""


class TencentSmsChannel(BaseSmsChannel):
    """腾讯云短信通道。"""

    def __init__(self, settings: TencentSmsSettings, *, client: httpx.AsyncClient | None = None) -> None:
        """初始化。

        Args:
            settings: 腾讯云短信配置。
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
        """发送一条模板短信。"""
        settings = self._settings
        if not settings.secret_id or not settings.secret_key or not settings.sdk_app_id or not settings.sign_name:
            return ChannelResult(
                delivered=False, error="腾讯云短信未配置（SecretId / SdkAppId / 签名）", retryable=False
            )
        body = {
            "PhoneNumberSet": [_normalize_phone(phone)],
            "SmsSdkAppId": settings.sdk_app_id,
            "SignName": settings.sign_name,
            "TemplateId": provider_template_id,
            "TemplateParamSet": [str(params.get(key, "")) for key in param_keys],
        }
        body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        headers = _signed_headers(
            body_text,
            secret_id=settings.secret_id,
            secret_key=settings.secret_key,
            timestamp=timestamp,
            region=settings.region,
            endpoint=settings.endpoint,
        )
        try:
            if self._client is not None:
                response = await self._client.post(settings.endpoint, content=body_text, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(settings.endpoint, content=body_text, headers=headers)
        except (httpx.HTTPError, OSError) as exc:
            _LOGGER.warning("腾讯云短信请求失败", phone=phone, error=str(exc))
            return ChannelResult(delivered=False, error=f"腾讯云短信请求失败：{exc}", retryable=True)
        if response.status_code >= 500:
            return ChannelResult(
                delivered=False, error=f"腾讯云短信服务不可用（HTTP {response.status_code}）", retryable=True
            )
        try:
            payload = cast("object", response.json())
        except ValueError:
            return ChannelResult(delivered=False, error="腾讯云短信响应非 JSON", retryable=True)
        if not isinstance(payload, dict):
            return ChannelResult(delivered=False, error="腾讯云短信响应非法", retryable=True)
        data = cast("dict[str, object]", payload).get("Response")
        if not isinstance(data, dict):
            return ChannelResult(delivered=False, error="腾讯云短信响应非法", retryable=True)
        response_data = cast("dict[str, object]", data)
        error = response_data.get("Error")
        if isinstance(error, dict):
            error_data = cast("dict[str, object]", error)
            code = str(error_data.get("Code") or "")
            message = str(error_data.get("Message") or "")
            _LOGGER.warning("腾讯云短信发送失败", phone=phone, code=code, message=message)
            return ChannelResult(
                delivered=False,
                error=f"腾讯云短信返回 {code}：{message}",
                retryable=code in _RETRYABLE_CODES,
            )
        statuses = response_data.get("SendStatusSet")
        if isinstance(statuses, list) and statuses:
            first = cast("list[object]", statuses)[0]
            if isinstance(first, dict):
                item = cast("dict[str, object]", first)
                code = str(item.get("Code") or "")
                if code == "Ok":
                    return ChannelResult(delivered=True, provider_message_id=str(item.get("SerialNo") or ""))
                return ChannelResult(
                    delivered=False,
                    error=f"腾讯云短信返回 {code}：{item.get('Message') or ''}",
                    retryable=code in _RETRYABLE_CODES,
                )
        return ChannelResult(delivered=False, error="腾讯云短信响应缺少发送状态", retryable=True)


def _signed_headers(
    body: str,
    *,
    secret_id: str,
    secret_key: str,
    timestamp: int,
    region: str,
    endpoint: str,
) -> ConcurrentStableDict[str, str]:
    """构造 TC3-HMAC-SHA256 签名请求头。"""
    host = urlparse(endpoint).netloc or "sms.tencentcloudapi.com"
    date = datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d")
    content_type = "application/json; charset=utf-8"
    canonical_headers = f"content-type:{content_type}\nhost:{host}\nx-tc-action:sendsms\n"
    signed_headers = "content-type;host;x-tc-action"
    hashed_body = hashlib.sha256(body.encode()).hexdigest()
    canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_body}"
    scope = f"{date}/sms/tc3_request"
    string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    secret_date = hmac.new(f"TC3{secret_key}".encode(), date.encode(), hashlib.sha256).digest()
    secret_service = hmac.new(secret_date, b"sms", hashlib.sha256).digest()
    secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
    signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return ConcurrentStableDict(
        {
            "Authorization": (
                f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "Content-Type": content_type,
            "Host": host,
            "X-TC-Action": "SendSms",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2021-01-11",
            "X-TC-Region": region,
        }
    )


def _normalize_phone(phone: str) -> str:
    """腾讯云手机号归一（统一 `+86` 前缀）。"""
    value = phone.strip().replace(" ", "").replace("-", "")
    if value.startswith("+"):
        return value
    if value.startswith("86"):
        return f"+{value}"
    return f"+86{value}"
