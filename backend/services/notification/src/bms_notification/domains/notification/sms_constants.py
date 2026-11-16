"""短信模板常量：渠道、场景（选项集）、内置事务性模板 code 与字段上限。"""

from bms_core.core.concurrent import ConcurrentStableList

__all__ = [
    "SMS_CHANNELS",
    "SMS_CHANNEL_ALIYUN",
    "SMS_CHANNEL_TENCENT",
    "SMS_SCENES",
    "SMS_SCENE_ALERT",
    "SMS_SCENE_CODE",
    "SMS_SCENE_DEFAULT",
    "SMS_SCENE_NOTIFY",
    "SMS_SCENE_OPTION_SET",
    "SMS_TEMPLATE_CODE_CAPTCHA",
    "SMS_TEMPLATE_CODE_PASSWORD_RESET",
    "SMS_TEMPLATE_CONTENT_MAX_BYTES",
    "SMS_TEMPLATE_NAME_MAX_LENGTH",
    "SMS_TEMPLATE_PROVIDER_MAX_LENGTH",
    "SMS_TEMPLATE_REMARK_MAX_LENGTH",
    "SMS_TEMPLATE_STATUSES",
    "SMS_TEMPLATE_STATUS_DISABLED",
    "SMS_TEMPLATE_STATUS_ENABLED",
]

SMS_CHANNEL_ALIYUN = "aliyun"
"""阿里云短信渠道。"""

SMS_CHANNEL_TENCENT = "tencent"
"""腾讯云短信渠道。"""

SMS_CHANNELS: ConcurrentStableList[str] = ConcurrentStableList((SMS_CHANNEL_ALIYUN, SMS_CHANNEL_TENCENT))
"""短信渠道取值（二选一）。"""

SMS_SCENE_CODE = "code"
"""场景：验证码。"""

SMS_SCENE_ALERT = "alert"
"""场景：告警。"""

SMS_SCENE_NOTIFY = "notify"
"""场景：通知。"""

SMS_SCENE_DEFAULT = SMS_SCENE_NOTIFY
"""场景缺省值。"""

SMS_SCENES: ConcurrentStableList[str] = ConcurrentStableList((SMS_SCENE_CODE, SMS_SCENE_ALERT, SMS_SCENE_NOTIFY))
"""短信场景取值。"""

SMS_SCENE_OPTION_SET = "bms.sms.scene"
"""短信场景选项集键（`deploy/registry/platform.toml`）。"""

SMS_TEMPLATE_STATUS_ENABLED = "enabled"
"""模板启用。"""

SMS_TEMPLATE_STATUS_DISABLED = "disabled"
"""模板停用。"""

SMS_TEMPLATE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (SMS_TEMPLATE_STATUS_ENABLED, SMS_TEMPLATE_STATUS_DISABLED)
)
"""模板状态取值。"""

SMS_TEMPLATE_CODE_CAPTCHA = "sms_captcha"
"""内置验证码短信模板 code。"""

SMS_TEMPLATE_CODE_PASSWORD_RESET = "sms_password_reset"
"""内置密码重置短信模板 code。"""

SMS_TEMPLATE_NAME_MAX_LENGTH = 128
"""模板名称长度上限。"""

SMS_TEMPLATE_REMARK_MAX_LENGTH = 255
"""备注长度上限。"""

SMS_TEMPLATE_PROVIDER_MAX_LENGTH = 64
"""厂商模板 ID 长度上限。"""

SMS_TEMPLATE_CONTENT_MAX_BYTES = 2000
"""正文 UTF-8 字节上限。"""
