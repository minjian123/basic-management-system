"""代码内置事务性短信模板（验证码 / 密码重置；平台默认、租户库可覆盖）。

- 云短信只允许厂商已审核模板：真实发送用厂商模板 ID + 参数，本清单提供本地文案与参数顺序；
- 厂商模板 ID 取 `[sms.<当前渠道>].captcha_template_id` / `password_reset_template_id`；
- 租户同 `(code, channel)` 行即覆盖，覆盖后以租户行（含厂商模板 ID）为准。
"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.objects import BaseValueObject
from bms_notification.domains.notification.sms_constants import (
    SMS_SCENE_CODE,
    SMS_TEMPLATE_CODE_CAPTCHA,
    SMS_TEMPLATE_CODE_PASSWORD_RESET,
)

__all__ = ["BUILTIN_SMS_TEMPLATES", "SmsTemplateDefault", "find_builtin_sms_template"]

PROVIDER_CAPTCHA_TEMPLATE_KEY = "captcha_template_id"
"""内置验证码模板的厂商模板 ID 配置键（`[sms.<渠道>]`）。"""

PROVIDER_PASSWORD_RESET_TEMPLATE_KEY = "password_reset_template_id"
"""内置密码重置模板的厂商模板 ID 配置键（`[sms.<渠道>]`）。"""


@dataclass(frozen=True)
class SmsTemplateDefault(BaseValueObject):
    """一条内置短信模板。"""

    code: str
    """模板 code。"""

    name: str
    """管理端显示名称。"""

    content: str
    """本地 Jinja2 文案（日志 / 替身发送用）。"""

    scene: str = SMS_SCENE_CODE
    """场景（选项集值）。"""

    provider_param_keys: ConcurrentStableFrozenList[str] = field(
        default_factory=lambda: ConcurrentStableFrozenList[str]()
    )
    """厂商参数名顺序（腾讯数组顺序；阿里云要求与模板变量名一致）。"""

    provider_config_key: str = ""
    """厂商模板 ID 在 `[sms.<渠道>]` 下的配置键。"""


BUILTIN_SMS_TEMPLATES: ConcurrentStableFrozenDict[str, SmsTemplateDefault] = ConcurrentStableFrozenDict(
    {
        SMS_TEMPLATE_CODE_CAPTCHA: SmsTemplateDefault(
            code=SMS_TEMPLATE_CODE_CAPTCHA,
            name="验证码短信",
            content="您的验证码是 {{ code }}，{{ minutes }} 分钟内有效，请勿泄露。",
            scene=SMS_SCENE_CODE,
            provider_param_keys=ConcurrentStableFrozenList(("code", "minutes")),
            provider_config_key=PROVIDER_CAPTCHA_TEMPLATE_KEY,
        ),
        SMS_TEMPLATE_CODE_PASSWORD_RESET: SmsTemplateDefault(
            code=SMS_TEMPLATE_CODE_PASSWORD_RESET,
            name="密码重置短信",
            content="您正在找回账号（{{ account }}）的密码，请在 {{ minutes }} 分钟内使用：{{ link or token }}。",
            scene=SMS_SCENE_CODE,
            provider_param_keys=ConcurrentStableFrozenList(("account", "minutes", "token", "link")),
            provider_config_key=PROVIDER_PASSWORD_RESET_TEMPLATE_KEY,
        ),
    }
)
"""内置事务性短信模板（验证码 / 密码重置）。"""


def find_builtin_sms_template(code: str) -> SmsTemplateDefault | None:
    """按 code 取内置短信模板。

    Args:
        code: 模板 code。

    Returns:
        SmsTemplateDefault | None: 内置模板；不存在为 None。
    """
    return BUILTIN_SMS_TEMPLATES.get(code)
