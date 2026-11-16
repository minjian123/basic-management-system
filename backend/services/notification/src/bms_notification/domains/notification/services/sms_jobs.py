"""短信发送作业：读取日志与作业负载，调用云短信通道并回写状态。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.logging import get_logger
from bms_core.jobs.base import BaseJobHandler, JobContext, JobResult
from bms_notification.domains.notification.channels.aliyun import AliyunSmsChannel
from bms_notification.domains.notification.channels.base import BaseSmsChannel
from bms_notification.domains.notification.channels.tencent import TencentSmsChannel
from bms_notification.domains.notification.delivery_constants import (
    DELIVERY_ERROR_MAX_LENGTH,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SUCCESS,
    SMS_JOB_TYPE,
)
from bms_notification.domains.notification.repositories.sms import SmsRepository
from bms_notification.domains.notification.sms_constants import SMS_CHANNEL_ALIYUN, SMS_CHANNEL_TENCENT

__all__ = ["SmsSendJob"]

_LOGGER = get_logger("bms")


class SmsSendJob(BaseJobHandler):
    """短信发送作业（幂等：日志已 success 时直接返回）。"""

    job_type = SMS_JOB_TYPE
    description = "按作业负载发送模板短信并回写 sys_sms_log"

    def __init__(self, channel: BaseSmsChannel | None = None) -> None:
        """初始化。

        Args:
            channel: 短信通道（测试注入替身；None 按负载渠道构建真实通道）。
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
        channel_name = str(ctx.payload.get("channel") or "")
        recipient = str(ctx.payload.get("recipient") or "")
        provider_template_id = str(ctx.payload.get("provider_template_id") or "")
        param_keys = _keys(ctx.payload.get("provider_param_keys"))
        params = _params(ctx.payload.get("params"))
        if log_id is None or not recipient or not provider_template_id or not channel_name:
            return JobResult.failed("短信发送负载非法", retryable=False)
        async with ctx.session() as session:
            repository = SmsRepository(session)
            log = await repository.get_log(log_id)
            if log is None:
                return JobResult.failed("短信发送记录不存在", retryable=False)
            if log.status == DELIVERY_STATUS_SUCCESS:
                return JobResult.success(message="短信已发送（幂等命中）")
            log.attempts = max(1, ctx.attempt)
            channel = self._channel if self._channel is not None else _build_channel(channel_name)
            if channel is None:
                log.status = DELIVERY_STATUS_FAILED
                log.error_msg = f"短信渠道配置非法：{channel_name}"[:DELIVERY_ERROR_MAX_LENGTH]
                await session.flush()
                return JobResult.failed(log.error_msg or "短信渠道配置非法", retryable=False)
            try:
                result = await channel.send(
                    phone=recipient,
                    provider_template_id=provider_template_id,
                    params=params,
                    param_keys=param_keys,
                )
            except Exception as exc:  # 通道实现异常按可重试处理，重试上限由作业中心兜底
                _LOGGER.warning("短信发送异常", log_id=log_id, error=str(exc))
                log.status = DELIVERY_STATUS_FAILED
                log.error_msg = f"通道异常：{exc}"[:DELIVERY_ERROR_MAX_LENGTH]
                await session.flush()
                return JobResult.failed(f"短信发送异常：{exc}", retryable=ctx.attempt < ctx.max_attempts)
            if result.delivered:
                log.status = DELIVERY_STATUS_SUCCESS
                log.error_msg = None
                log.sent_at = datetime.now(UTC).replace(tzinfo=None)
                await session.flush()
                return JobResult.success(ConcurrentStableDict({"log_id": str(log_id)}), message="短信发送成功")
            log.status = DELIVERY_STATUS_FAILED
            log.error_msg = (result.error or "发送失败")[:DELIVERY_ERROR_MAX_LENGTH]
            await session.flush()
            _LOGGER.warning("短信发送失败", log_id=log_id, error=log.error_msg)
            return JobResult.failed(
                log.error_msg or "短信发送失败",
                retryable=result.retryable and ctx.attempt < ctx.max_attempts,
            )


def _build_channel(name: str) -> BaseSmsChannel | None:
    """按负载渠道构建真实通道（配置取全局）。"""
    settings = get_settings().sms
    if name == SMS_CHANNEL_ALIYUN:
        return AliyunSmsChannel(settings.aliyun)
    if name == SMS_CHANNEL_TENCENT:
        return TencentSmsChannel(settings.tencent)
    return None


def _int_value(value: object) -> int | None:
    """把负载中的 id 转 int（非法返回 None）。"""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _keys(value: object) -> ConcurrentStableList[str]:
    """解析参数名顺序（非法按空）。"""
    if isinstance(value, list):
        return ConcurrentStableList(str(item) for item in cast("list[object]", value))
    return ConcurrentStableList()


def _params(value: object) -> ConcurrentStableDict[str, str]:
    """解析参数映射（非法按空）。"""
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return ConcurrentStableDict({str(key): str(item) for key, item in mapping.items()})
    return ConcurrentStableDict()
