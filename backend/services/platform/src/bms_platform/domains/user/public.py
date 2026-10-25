"""用户业务域公共出口（D2 唯一跨域引用面）。

对外提供「用户主数据」的最小可用面：用户仓储与用户模型（角色域做分配校验与展示时使用）。
**本模块只做再导出**，不承载业务规则；域内其他模块不得被跨域导入（D1 拦截）。
"""

from bms_core.models.platform.user import (
    LOCK_TYPE_FAIL_LIMIT as LOCK_TYPE_FAIL_LIMIT,
)
from bms_core.models.platform.user import (
    LOCK_TYPE_INACTIVE as LOCK_TYPE_INACTIVE,
)
from bms_core.models.platform.user import (
    LOCK_TYPE_MANUAL as LOCK_TYPE_MANUAL,
)
from bms_core.models.platform.user import (
    LOCK_TYPES as LOCK_TYPES,
)
from bms_core.models.platform.user import (
    UNLOCK_MODE_AUTO as UNLOCK_MODE_AUTO,
)
from bms_core.models.platform.user import (
    UNLOCK_MODE_MANUAL as UNLOCK_MODE_MANUAL,
)
from bms_core.models.platform.user import (
    UNLOCK_MODES as UNLOCK_MODES,
)
from bms_core.models.platform.user import (
    SysAccountLock as SysAccountLock,
)
from bms_core.models.platform.user import (
    SysUser as SysUser,
)
from bms_platform.domains.user.repositories.user import UserRepository as UserRepository

__all__ = [
    "LOCK_TYPES",
    "LOCK_TYPE_FAIL_LIMIT",
    "LOCK_TYPE_INACTIVE",
    "LOCK_TYPE_MANUAL",
    "UNLOCK_MODES",
    "UNLOCK_MODE_AUTO",
    "UNLOCK_MODE_MANUAL",
    "SysAccountLock",
    "SysUser",
    "UserRepository",
]
