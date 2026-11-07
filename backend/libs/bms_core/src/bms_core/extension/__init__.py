"""扩展点声明与装配校验能力域（07D `02_01` ~ `02_05`）。

对外统一从本包导入（`from bms_core.extension import ExtensionRequirement`）。
"""

from bms_core.extension.base import (
    AUDIT_EXTENSION_KEY,
    DEFAULT_EXTENSION_ORDER,
    ERROR_MAPPING_KEY,
    EXTENSION_POINT_KEYS,
    EXTENSION_REQUIREMENT_NAME_RE,
    MAX_EXTENSION_ORDER,
    MIN_EXTENSION_ORDER,
    QUOTA_PROJECTION_KEY,
    RESOURCE_ACL_KEY,
    SCOPE_RULE_KEY,
    ExtensionRequirement,
    requirements_by_key,
    verify_extension_requirements,
)

__all__ = [
    "AUDIT_EXTENSION_KEY",
    "DEFAULT_EXTENSION_ORDER",
    "ERROR_MAPPING_KEY",
    "EXTENSION_POINT_KEYS",
    "EXTENSION_REQUIREMENT_NAME_RE",
    "MAX_EXTENSION_ORDER",
    "MIN_EXTENSION_ORDER",
    "QUOTA_PROJECTION_KEY",
    "RESOURCE_ACL_KEY",
    "SCOPE_RULE_KEY",
    "ExtensionRequirement",
    "requirements_by_key",
    "verify_extension_requirements",
]
