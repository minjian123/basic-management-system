"""权限元数据业务域公共出口（D2 唯一跨域引用面）。

对外提供：业务码 / 动作码 / 权限码仓储与服务、权限元数据模型（角色域做授权校验与停用前置探测时使用）。
**本模块只做再导出**，不承载业务规则。
"""

from bms_core.models.platform.permission_meta import (
    SysAction as SysAction,
)
from bms_core.models.platform.permission_meta import (
    SysActionI18n as SysActionI18n,
)
from bms_core.models.platform.permission_meta import (
    SysBusiness as SysBusiness,
)
from bms_core.models.platform.permission_meta import (
    SysBusinessI18n as SysBusinessI18n,
)
from bms_core.models.platform.permission_meta import (
    SysPermission as SysPermission,
)
from bms_platform.domains.permission_meta.repositories.business import (
    ActionRepository as ActionRepository,
)
from bms_platform.domains.permission_meta.repositories.business import (
    BusinessRepository as BusinessRepository,
)
from bms_platform.domains.permission_meta.repositories.business import (
    PermissionRepository as PermissionRepository,
)
from bms_platform.domains.permission_meta.services.permission_meta import (
    PermissionMetadataService as PermissionMetadataService,
)

__all__ = [
    "ActionRepository",
    "BusinessRepository",
    "PermissionMetadataService",
    "PermissionRepository",
    "SysAction",
    "SysActionI18n",
    "SysBusiness",
    "SysBusinessI18n",
    "SysPermission",
]
