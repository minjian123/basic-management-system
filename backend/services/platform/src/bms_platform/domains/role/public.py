"""角色业务域公共出口（D2 唯一跨域引用面）。

只交三类：**不可变 DTO**（`dto.py`）、**领域服务接口**（`ports.py`）与**白名单常量 / 能力插件**
（运行期不可变值域与字段权限 provider，登记于 `deploy/boundaries/domain_public_export_baseline.json`）。
实现类（`RoleQueryService` / `RoleAssignmentService` / `RoleGrantReader` / `RoleReferenceService` /
`SeparationGuard` / 两个解析器）与仓储、ORM 模型**不出本出口**——实现由 `bms_platform.wiring`
构造后注入，跨域消费方只持协议与 DTO。
"""

from bms_core.models.platform.role import (
    PERM_TYPE_FORM as PERM_TYPE_FORM,
)
from bms_core.models.platform.role import (
    PERM_TYPE_MENU as PERM_TYPE_MENU,
)
from bms_core.models.platform.role import (
    PERM_TYPE_PERMISSION as PERM_TYPE_PERMISSION,
)
from bms_core.models.platform.role import (
    ROLE_TYPE_CUSTOM as ROLE_TYPE_CUSTOM,
)
from bms_core.permission.field import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY as DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
)
from bms_platform.domains.role.dto import (
    AssignedUser as AssignedUser,
)
from bms_platform.domains.role.dto import (
    RoleDataScopeEntry as RoleDataScopeEntry,
)
from bms_platform.domains.role.dto import (
    RoleDetailSnapshot as RoleDetailSnapshot,
)
from bms_platform.domains.role.dto import (
    RoleFieldGrant as RoleFieldGrant,
)
from bms_platform.domains.role.dto import (
    RolePermissionEntry as RolePermissionEntry,
)
from bms_platform.domains.role.dto import (
    RoleSummary as RoleSummary,
)
from bms_platform.domains.role.permission.field_provider import (
    StaticFieldPermissionProvider as StaticFieldPermissionProvider,
)
from bms_platform.domains.role.permission.field_provider import (
    build_static_field_provider as build_static_field_provider,
)
from bms_platform.domains.role.ports import (
    RoleAssignmentPort as RoleAssignmentPort,
)
from bms_platform.domains.role.ports import (
    RoleGrantPort as RoleGrantPort,
)
from bms_platform.domains.role.ports import (
    RoleQueryPort as RoleQueryPort,
)
from bms_platform.domains.role.ports import (
    RoleReferencePort as RoleReferencePort,
)
from bms_platform.domains.role.ports import (
    SeparationPort as SeparationPort,
)

__all__ = [
    "DEFAULT_FIELD_PERMISSION_PROVIDER_KEY",
    "PERM_TYPE_FORM",
    "PERM_TYPE_MENU",
    "PERM_TYPE_PERMISSION",
    "ROLE_TYPE_CUSTOM",
    "AssignedUser",
    "RoleAssignmentPort",
    "RoleDataScopeEntry",
    "RoleDetailSnapshot",
    "RoleFieldGrant",
    "RoleGrantPort",
    "RolePermissionEntry",
    "RoleQueryPort",
    "RoleReferencePort",
    "RoleSummary",
    "SeparationPort",
    "StaticFieldPermissionProvider",
    "build_static_field_provider",
]
