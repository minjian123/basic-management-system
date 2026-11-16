"""邮件模板常量：状态、来源、code 规则与字段上限。"""

from bms_core.core.concurrent import ConcurrentStableList

__all__ = [
    "MAIL_TEMPLATE_CODE_PATTERN",
    "MAIL_TEMPLATE_CONTENT_MAX_BYTES",
    "MAIL_TEMPLATE_NAME_MAX_LENGTH",
    "MAIL_TEMPLATE_REMARK_MAX_LENGTH",
    "MAIL_TEMPLATE_SOURCE_BUILTIN",
    "MAIL_TEMPLATE_SOURCE_TENANT",
    "MAIL_TEMPLATE_STATUSES",
    "MAIL_TEMPLATE_STATUS_DISABLED",
    "MAIL_TEMPLATE_STATUS_ENABLED",
    "MAIL_TEMPLATE_SUBJECT_MAX_LENGTH",
]

MAIL_TEMPLATE_STATUS_ENABLED = "enabled"
"""模板启用。"""

MAIL_TEMPLATE_STATUS_DISABLED = "disabled"
"""模板停用（租户显式停用时不回落内置默认）。"""

MAIL_TEMPLATE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (MAIL_TEMPLATE_STATUS_ENABLED, MAIL_TEMPLATE_STATUS_DISABLED)
)
"""模板状态取值。"""

MAIL_TEMPLATE_SOURCE_TENANT = "tenant"
"""来源：租户库模板。"""

MAIL_TEMPLATE_SOURCE_BUILTIN = "builtin"
"""来源：代码内置默认模板（只读、无 id）。"""

MAIL_TEMPLATE_CODE_PATTERN = r"^[a-z][a-z0-9_.-]{1,63}$"
"""模板 code 规则（小写字母开头，2~64 位；创建后不可改）。"""

MAIL_TEMPLATE_NAME_MAX_LENGTH = 128
"""模板名称长度上限。"""

MAIL_TEMPLATE_REMARK_MAX_LENGTH = 255
"""备注长度上限。"""

MAIL_TEMPLATE_SUBJECT_MAX_LENGTH = 256
"""主题长度上限。"""

MAIL_TEMPLATE_CONTENT_MAX_BYTES = 60000
"""正文 UTF-8 字节上限。"""
