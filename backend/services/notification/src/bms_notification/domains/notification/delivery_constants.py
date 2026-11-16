"""邮件 / 短信外发公共常量：日志状态、限长与作业类型。

- 日志状态只四态：待发送 / 成功 / 失败 / 跳过（免打扰）；
- 邮件正文不落日志、短信正文脱敏，长度上限与沙箱输出上限同口径；
- 作业类型与 `deploy/registry/platform.toml` 的 `[[jobs]]` 声明一致。
"""

from bms_core.core.concurrent import ConcurrentStableList

__all__ = [
    "DELIVERY_ATTEMPTS_DEFAULT",
    "DELIVERY_ERROR_MAX_LENGTH",
    "DELIVERY_IDEMPOTENCY_KEY_MAX_LENGTH",
    "DELIVERY_STATUSES",
    "DELIVERY_STATUS_FAILED",
    "DELIVERY_STATUS_PENDING",
    "DELIVERY_STATUS_SKIPPED",
    "DELIVERY_STATUS_SUCCESS",
    "MAIL_JOB_TYPE",
    "MAIL_LOG_CHANNEL",
    "MAIL_RENDER_MAX_BYTES",
    "MAIL_SUBJECT_MAX_LENGTH",
    "MAIL_TEMPLATE_CONTENT_MAX_BYTES",
    "SMS_JOB_TYPE",
    "SMS_RENDER_MAX_BYTES",
    "SMS_TEMPLATE_CONTENT_MAX_BYTES",
]

DELIVERY_STATUS_PENDING = "pending"
"""已受理待发送。"""

DELIVERY_STATUS_SUCCESS = "success"
"""发送成功。"""

DELIVERY_STATUS_FAILED = "failed"
"""发送失败（含模板停用 / 渠道未配置 / 厂商返回错误）。"""

DELIVERY_STATUS_SKIPPED = "skipped"
"""被偏好过滤跳过（当前只有免打扰）。"""

DELIVERY_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (DELIVERY_STATUS_PENDING, DELIVERY_STATUS_SUCCESS, DELIVERY_STATUS_FAILED, DELIVERY_STATUS_SKIPPED)
)
"""发送记录状态取值。"""

DELIVERY_ERROR_MAX_LENGTH = 512
"""错误摘要长度上限（与死信 / 作业错误摘要同口径）。"""

DELIVERY_IDEMPOTENCY_KEY_MAX_LENGTH = 128
"""幂等键长度上限。"""

DELIVERY_ATTEMPTS_DEFAULT = 0
"""新建日志的已尝试次数。"""

MAIL_LOG_CHANNEL = "smtp"
"""邮件日志渠道标识（当前只有 SMTP）。"""

MAIL_JOB_TYPE = "notification.mail.send"
"""邮件发送作业类型。"""

SMS_JOB_TYPE = "notification.sms.send"
"""短信发送作业类型。"""

MAIL_SUBJECT_MAX_LENGTH = 256
"""邮件主题长度上限（字符）。"""

MAIL_TEMPLATE_CONTENT_MAX_BYTES = 60000
"""邮件模板正文与渲染输出上限（UTF-8 字节；MySQL TEXT 上限内）。"""

MAIL_RENDER_MAX_BYTES = MAIL_TEMPLATE_CONTENT_MAX_BYTES
"""邮件沙箱渲染输出上限（UTF-8 字节）。"""

SMS_TEMPLATE_CONTENT_MAX_BYTES = 2000
"""短信模板正文上限（UTF-8 字节）。"""

SMS_RENDER_MAX_BYTES = SMS_TEMPLATE_CONTENT_MAX_BYTES
"""短信沙箱渲染输出上限（UTF-8 字节）。"""
