"""`form_key` 构建期清单（系统字段 `form_key` 的跨表登记与全局唯一校验）。"""

from bms_core.registry.forms import (
    FORM_CATALOG,
    FORM_KEY_PATTERN,
    FormKind,
    FormRecord,
    FormRegistry,
    FormStatus,
    merge_form_records,
)

__all__ = [
    "FORM_CATALOG",
    "FORM_KEY_PATTERN",
    "FormKind",
    "FormRecord",
    "FormRegistry",
    "FormStatus",
    "merge_form_records",
]
