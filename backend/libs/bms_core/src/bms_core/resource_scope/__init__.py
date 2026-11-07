"""作用域资源归属能力域（07D `01_01`）：三级作用域值对象与资源类型注册视图。

对外统一从本包导入（`from bms_core.resource_scope import ResourceScopeKey`）；
与 `bms_core/scope/`（数据范围）职责正交，见 `base.py` 模块文档。
"""

from bms_core.resource_scope.base import (
    DEFAULT_RESOURCE_KEY_MAX_LENGTH,
    MAX_RESOURCE_KEY_LENGTH,
    MODULE_KEY_RE,
    REMOVAL_POLICIES,
    REMOVAL_POLICY_ARCHIVE,
    REMOVAL_POLICY_PURGE,
    RESOURCE_KEY_PATTERN_DEFAULT,
    RESOURCE_KEY_RE,
    RESOURCE_TYPE_KEY_RE,
    SCOPE_RESOURCE_ADMIN_STATUSES,
    SCOPE_RESOURCE_DISABLED,
    SCOPE_RESOURCE_ENABLED,
    SCOPE_RESOURCE_RETIRED,
    SCOPE_RESOURCE_STATUSES,
    ResourceScopeKey,
    ScopeResourceTypeRecord,
    find_scope_resource_type,
    register_scope_resource_types,
    reset_scope_resource_types,
    scope_resource_type_issues,
    scope_resource_type_key,
    scope_resource_type_view,
    scope_resource_types_of,
)

__all__ = [
    "DEFAULT_RESOURCE_KEY_MAX_LENGTH",
    "MAX_RESOURCE_KEY_LENGTH",
    "MODULE_KEY_RE",
    "REMOVAL_POLICIES",
    "REMOVAL_POLICY_ARCHIVE",
    "REMOVAL_POLICY_PURGE",
    "RESOURCE_KEY_PATTERN_DEFAULT",
    "RESOURCE_KEY_RE",
    "RESOURCE_TYPE_KEY_RE",
    "SCOPE_RESOURCE_ADMIN_STATUSES",
    "SCOPE_RESOURCE_DISABLED",
    "SCOPE_RESOURCE_ENABLED",
    "SCOPE_RESOURCE_RETIRED",
    "SCOPE_RESOURCE_STATUSES",
    "ResourceScopeKey",
    "ScopeResourceTypeRecord",
    "find_scope_resource_type",
    "register_scope_resource_types",
    "reset_scope_resource_types",
    "scope_resource_type_issues",
    "scope_resource_type_key",
    "scope_resource_type_view",
    "scope_resource_types_of",
]
