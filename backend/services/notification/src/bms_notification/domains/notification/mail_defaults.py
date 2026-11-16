"""代码内置邮件默认模板（平台默认、租户库可覆盖）。

- 不物化种子行：读取先租户库、无同 code 模板回落本清单；
- 修改默认模板随发版生效，租户覆盖行优先；
- 内置清单只读，租户同 code 行即覆盖。
"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.objects import BaseValueObject

__all__ = ["BUILTIN_MAIL_TEMPLATES", "MailTemplateDefault", "find_builtin_mail_template"]

_ZH = "zh-CN"
_EN = "en-US"


@dataclass(frozen=True)
class MailTemplateDefault(BaseValueObject):
    """一条内置邮件模板（多语言主题 / 正文）。"""

    code: str
    """模板 code。"""

    name: str
    """管理端显示名称。"""

    remark: str = ""
    """备注。"""

    i18n: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenDict[str, str]] = field(
        default_factory=lambda: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenDict[str, str]]()
    )
    """语言 → （subject / content）。"""


BUILTIN_MAIL_TEMPLATES: ConcurrentStableFrozenDict[str, MailTemplateDefault] = ConcurrentStableFrozenDict(
    {
        "approval_todo": MailTemplateDefault(
            code="approval_todo",
            name="审批待办提醒",
            remark="内置默认（代码提供，租户可覆盖）",
            i18n=ConcurrentStableFrozenDict(
                {
                    _ZH: ConcurrentStableFrozenDict(
                        {
                            "subject": "【BMS】待办提醒：{{ title }}",
                            "content": (
                                "<p>您有一条新的待办：</p><p><strong>{{ title }}</strong></p>"
                                "<p>{{ content }}</p><p>请登录系统及时处理。</p>"
                            ),
                        }
                    ),
                    _EN: ConcurrentStableFrozenDict(
                        {
                            "subject": "[BMS] Todo: {{ title }}",
                            "content": (
                                "<p>You have a new todo:</p><p><strong>{{ title }}</strong></p>"
                                "<p>{{ content }}</p><p>Please sign in and handle it in time.</p>"
                            ),
                        }
                    ),
                }
            ),
        ),
        "system_alert": MailTemplateDefault(
            code="system_alert",
            name="系统告警通知",
            remark="内置默认（代码提供，租户可覆盖）",
            i18n=ConcurrentStableFrozenDict(
                {
                    _ZH: ConcurrentStableFrozenDict(
                        {
                            "subject": "【BMS】系统告警：{{ title }}",
                            "content": (
                                "<p>系统产生一条告警：</p><p><strong>{{ title }}</strong></p><p>{{ content }}</p>"
                            ),
                        }
                    ),
                    _EN: ConcurrentStableFrozenDict(
                        {
                            "subject": "[BMS] System alert: {{ title }}",
                            "content": (
                                "<p>A system alert was raised:</p><p><strong>{{ title }}</strong></p>"
                                "<p>{{ content }}</p>"
                            ),
                        }
                    ),
                }
            ),
        ),
    }
)
"""内置邮件默认模板（审批待办 / 系统告警；中英文）。"""


def find_builtin_mail_template(code: str) -> MailTemplateDefault | None:
    """按 code 取内置邮件模板。

    Args:
        code: 模板 code。

    Returns:
        MailTemplateDefault | None: 内置模板；不存在为 None。
    """
    return BUILTIN_MAIL_TEMPLATES.get(code)
