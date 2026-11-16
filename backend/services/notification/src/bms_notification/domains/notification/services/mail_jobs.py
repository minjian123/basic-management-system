"""邮件发送作业：读取日志与作业负载，调用 SMTP 通道并回写状态。"""

from __future__ import annotations

from datetime import UTC, datetime

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.logging import get_logger
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_notification.domains.notification.channels.base import BaseMailChannel
from bms_notification.domains.notification.channels.smtp import SmtpMailChannel
from bms_notification.domains.notification.delivery_constants import (
    DELIVERY_ERROR_MAX_LENGTH,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SUCCESS,
    MAIL_JOB_TYPE,
)
from bms_notification.domains.notification.repositories.mail import MailRepository

__all__ = ["MailSendJob"]

_LOGGER = get_logger("bms")


class MailSendJob(BaseJobHandler):
    """邮件发送作业（幂等：日志已 success 时直接返回）。"""

    job_type = MAIL_JOB_TYPE
    description = "按作业负载发送邮件并回写 sys_mail_log"

    def __init__(self, channel: BaseMailChannel | None = None) -> None:
        """初始化。

        Args:
            channel: 邮件通道（测试注入替身；None 按配置构建 SMTP）。
        """
        self._channel = channel

    async def run(self, ctx: JobContext) -> JobResult:
        """执行发送。

        Args:
            ctx: 作业上下文。

        Returns:
            JobResult: 成功 / 可重试失败 / 永久失败。
        """
        log_id = _int_value(ctx.payload.get("log_id"))
        recipient = str(ctx.payload.get("recipient") or "")
        subject = str(ctx.payload.get("title") or "")
        content = str(ctx.payload.get("content") or "")
        html = bool(ctx.payload.get("html"))
        if log_id is None or not recipient or not subject:
            return JobResult.failed("邮件发送负载非法", retryable=False)
        async with ctx.session() as session:
            repository = MailRepository(session)
            log = await repository.get_log(log_id)
            if log is None:
                return JobResult.failed("邮件发送记录不存在", retryable=False)
            if log.status == DELIVERY_STATUS_SUCCESS:
                return JobResult.success(message="邮件已发送（幂等命中）")
            log.attempts = max(1, ctx.attempt)
            channel = self._channel if self._channel is not None else SmtpMailChannel(get_settings().mail)
            try:
                result = await channel.send(recipient=recipient, subject=subject, content=content, html=html)
            except Exception as exc:  # 通道实现异常按可重试处理，重试上限由作业中心兜底
                _LOGGER.warning("邮件发送异常", log_id=log_id, error=str(exc))
                log.status = DELIVERY_STATUS_FAILED
                log.error_msg = f"通道异常：{exc}"[:DELIVERY_ERROR_MAX_LENGTH]
                await session.flush()
                return JobResult.failed(f"邮件发送异常：{exc}", retryable=ctx.attempt < ctx.max_attempts)
            if result.delivered:
                log.status = DELIVERY_STATUS_SUCCESS
                log.error_msg = None
                log.sent_at = datetime.now(UTC).replace(tzinfo=None)
                await session.flush()
                return JobResult.success(ConcurrentStableDict({"log_id": str(log_id)}), message="邮件发送成功")
            log.status = DELIVERY_STATUS_FAILED
            log.error_msg = (result.error or "发送失败")[:DELIVERY_ERROR_MAX_LENGTH]
            await session.flush()
            _LOGGER.warning("邮件发送失败", log_id=log_id, error=log.error_msg)
            return JobResult.failed(
                log.error_msg or "邮件发送失败",
                retryable=result.retryable and ctx.attempt < ctx.max_attempts,
            )


def _int_value(value: object) -> int | None:
    """把负载中的 id 转 int（非法返回 None）。"""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None
