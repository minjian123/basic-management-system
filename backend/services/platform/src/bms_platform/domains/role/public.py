"""角色业务域公共出口（D2 唯一跨域引用面）。

对外提供：角色授权仓储（角色 / 用户-角色 / 角色权限 / 数据范围）、职责分离守卫、角色主体解析器、
字段权限 provider 工厂与角色模型常量（用户域编排用户-角色绑定、权限元数据域解析主体角色时使用）。
**本模块只做再导出**，不承载业务规则。
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
from bms_core.models.platform.role import (
    SysDataScope as SysDataScope,
)
from bms_core.models.platform.role import (
    SysRole as SysRole,
)
from bms_core.models.platform.role import (
    SysRoleField as SysRoleField,
)
from bms_core.models.platform.role import (
    SysRolePermission as SysRolePermission,
)
from bms_core.models.platform.role import (
    SysUserRole as SysUserRole,
)
from bms_core.permission.field import (
    DEFAULT_FIELD_PERMISSION_PROVIDER_KEY as DEFAULT_FIELD_PERMISSION_PROVIDER_KEY,
)
from bms_platform.domains.role.permission.field_provider import (
    StaticFieldPermissionProvider as StaticFieldPermissionProvider,
)
from bms_platform.domains.role.permission.field_provider import (
    build_static_field_provider as build_static_field_provider,
)
from bms_platform.domains.role.repositories.reference import MetadataReferenceRepository as MetadataReferenceRepository
from bms_platform.domains.role.repositories.role import (
    DataScopeRepository as DataScopeRepository,
)
from bms_platform.domains.role.repositories.role import (
    RolePermissionRepository as RolePermissionRepository,
)
from bms_platform.domains.role.repositories.role import (
    RoleRepository as RoleRepository,
)
from bms_platform.domains.role.repositories.role import (
    UserRoleRepository as UserRoleRepository,
)
from bms_platform.domains.role.services.permission_subject import (
    DirectRoleResolver as DirectRoleResolver,
)
from bms_platform.domains.role.services.permission_subject import (
    OrgRoleResolver as OrgRoleResolver,
)
from bms_platform.domains.role.services.separation import SeparationGuard as SeparationGuard

__all__ = [
    "DEFAULT_FIELD_PERMISSION_PROVIDER_KEY",
    "PERM_TYPE_FORM",
    "PERM_TYPE_MENU",
    "PERM_TYPE_PERMISSION",
    "ROLE_TYPE_CUSTOM",
    "DataScopeRepository",
    "DirectRoleResolver",
    "MetadataReferenceRepository",
    "OrgRoleResolver",
    "RolePermissionRepository",
    "RoleRepository",
    "SeparationGuard",
    "StaticFieldPermissionProvider",
    "SysDataScope",
    "SysRole",
    "SysRoleField",
    "SysRolePermission",
    "SysUserRole",
    "UserRoleRepository",
    "build_static_field_provider",
]
