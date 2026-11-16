"""SMTP 邮件通道（aiosmtplib）：真实发送 + 失败分类。"""

from __future__ import annotations

from email.message import EmailMessage
from email.utils import formataddr

import aiosmtplib

from bms_core.core.config import MailSettings
from bms_core.core.logging import get_logger
from bms_notification.domains.notification.channels.base import BaseMailChannel, ChannelResult

__all__ = ["SmtpMailChannel"]

_LOGGER = get_logger("bms")


class SmtpMailChannel(BaseMailChannel):
    """SMTP 邮件通道（按 `[mail]` 配置发送）。"""

    def __init__(self, settings: MailSettings) -> None:
        """初始化。

        Args:
            settings: 邮件配置。
        """
        self._settings = settings

    async def send(self, *, recipient: str, subject: str, content: str, html: bool) -> ChannelResult:
        """发送一封邮件。

        Args:
            recipient: 收件邮箱。
            subject: 主题。
            content: 正文。
            html: 正文是否 HTML。

        Returns:
            ChannelResult: 发送结果。
        """
        settings = self._settings
        if not settings.smtp_host or not settings.smtp_from:
            return ChannelResult(delivered=False, error="SMTP 未配置（host / from）", retryable=False)
        message = EmailMessage()
        message["From"] = formataddr((settings.smtp_from_name, settings.smtp_from))
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(content, subtype="html" if html else "plain", charset="utf-8")
        security = settings.smtp_security.strip().lower()
        try:
            await aiosmtplib.send(
                message,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username or None,
                password=settings.smtp_password or None,
                timeout=settings.smtp_timeout_seconds,
                use_tls=security == "ssl",
                start_tls=security == "starttls",
            )
        except aiosmtplib.SMTPAuthenticationError as exc:
            _LOGGER.warning("SMTP 认证失败", recipient=recipient, error=str(exc))
            return ChannelResult(delivered=False, error=f"SMTP 认证失败：{exc}", retryable=False)
        except aiosmtplib.SMTPRecipientsRefused as exc:
            _LOGGER.warning("SMTP 收件人被拒绝", recipient=recipient, error=str(exc))
            return ChannelResult(delivered=False, error=f"SMTP 收件人被拒绝：{exc}", retryable=False)
        except aiosmtplib.SMTPResponseException as exc:
            retryable = int(getattr(exc, "code", 0) or 0) < 500
            _LOGGER.warning("SMTP 响应异常", recipient=recipient, code=getattr(exc, "code", 0), error=str(exc))
            return ChannelResult(
                delivered=False, error=f"SMTP 响应异常（{getattr(exc, 'code', 0)}）：{exc}", retryable=retryable
            )
        except (aiosmtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
            _LOGGER.warning("SMTP 连接失败", recipient=recipient, error=str(exc))
            return ChannelResult(delivered=False, error=f"SMTP 连接失败：{exc}", retryable=True)
        except aiosmtplib.SMTPException as exc:
            _LOGGER.warning("SMTP 发送失败", recipient=recipient, error=str(exc))
            return ChannelResult(delivered=False, error=f"SMTP 发送失败：{exc}", retryable=True)
        return ChannelResult(delivered=True)
