"""开通所需默认数据种子（14_04 自 `ops` 下沉）：平台 / 身份 / 账号侧内置数据。

四个种子模块（口径见《平台可扩展性规划》三层模型「基座可承载开通所需默认种子，不承载业务运营逻辑」）：

- `platform`：平台租户 RBAC（`platform_admin` / `platform_ops` 角色与授权）；
- `rbac`：三类内置管理员角色与授权（系统 / 安全 / 审计三权互斥）；
- `sso`：演示 IdP 行与可选用户映射；
- `user`：初始系统管理员账号（含租户库名基解析）。

各模块的 CLI 入口（`build_parser` / `main`）随实现一并下沉，`ops` 侧同名脚本为一行调用薄壳，
`python -m ops.<script>` 的命令、参数与退出码不变。
"""

from bms_core.tenant.seed.contract import ExpectedRow
from bms_core.tenant.seed.platform import (
    PLATFORM_ADMIN_ROLE_CODE,
    PLATFORM_OPS_ROLE_CODE,
    PlatformSeedOutcome,
    seed_platform_rbac,
)
from bms_core.tenant.seed.rbac import (
    BUILTIN_ADMIN_ROLES,
    ROLE_AUDIT_ADMIN,
    ROLE_SECURITY_ADMIN,
    ROLE_SYSTEM_ADMIN,
    seed_rbac,
)
from bms_core.tenant.seed.rbac import (
    SeedOutcome as RbacSeedOutcome,
)
from bms_core.tenant.seed.sso import DEFAULT_IDP_KEY, seed_identity_provider, seed_user_mapping
from bms_core.tenant.seed.user import SeedOutcome as UserSeedOutcome
from bms_core.tenant.seed.user import seed_user

__all__ = [
    "BUILTIN_ADMIN_ROLES",
    "DEFAULT_IDP_KEY",
    "PLATFORM_ADMIN_ROLE_CODE",
    "PLATFORM_OPS_ROLE_CODE",
    "ROLE_AUDIT_ADMIN",
    "ROLE_SECURITY_ADMIN",
    "ROLE_SYSTEM_ADMIN",
    "ExpectedRow",
    "PlatformSeedOutcome",
    "RbacSeedOutcome",
    "UserSeedOutcome",
    "seed_identity_provider",
    "seed_platform_rbac",
    "seed_rbac",
    "seed_user",
    "seed_user_mapping",
]
