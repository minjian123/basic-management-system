"""平台服务 **种子分支处理器**（07B `02_03`）：把 9 个种子入口挂进 XA 分支注册表。

与 `branch_handlers.py`（用户 / 角色保存编排）同构：`op` → 本服务已有实现，
由基座分支执行器在**已开启的两阶段分支事务**的连接上调用。

**为什么单独一个模块**：种子分支是「运维初始化」用途，与业务编排（用户保存 / 角色保存）
职责不同；分文件便于按需注册与排障定位。
"""

from typing import TYPE_CHECKING

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.tenant.seed.platform import (
    seed_platform_grants_entry,
    seed_platform_roles_entry,
)
from bms_core.tenant.seed.rbac import seed_rbac_grants_entry, seed_rbac_roles_entry
from bms_core.transaction.base import BranchHandlerRegistry

if TYPE_CHECKING:
    pass

__all__ = ["SEED_OPS", "register_seed_handlers"]

SEED_OPS: tuple[str, ...] = (
    "seed-module",
    "seed-tables",
    "seed-menu",
    "seed-tenant",
    "seed-config",
    "seed-platform-role",
    "seed-platform-grant",
    "seed-rbac-role",
    "seed-rbac-grant",
)
"""平台侧登记的种子分支操作名（与 `deploy/registry/platform.toml` 的 `name` 一一对应）。"""


def register_seed_handlers(registry: BranchHandlerRegistry) -> BranchHandlerRegistry:
    """把 9 个平台种子入口登记进分支处理器注册表（幂等：已登记即跳过）。

    Args:
        registry: 分支处理器注册表（由 `build_branch_handlers` 传入并复用）。

    Returns:
        BranchHandlerRegistry: 同一个注册表（便于链式调用）。
    """
    from bms_core.tenant.seed.config import seed_configs_entry
    from bms_core.tenant.seed.menu import seed_menu_entry
    from bms_core.tenant.seed.module import seed_modules_entry
    from bms_core.tenant.seed.tables import seed_tables_entry
    from bms_core.tenant.seed.tenant import seed_tenants_entry

    handlers: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    handlers.set("seed-module", seed_modules_entry)
    handlers.set("seed-tables", seed_tables_entry)
    handlers.set("seed-menu", seed_menu_entry)
    handlers.set("seed-tenant", seed_tenants_entry)
    handlers.set("seed-config", seed_configs_entry)
    handlers.set("seed-platform-role", seed_platform_roles_entry)
    handlers.set("seed-platform-grant", seed_platform_grants_entry)
    handlers.set("seed-rbac-role", seed_rbac_roles_entry)
    handlers.set("seed-rbac-grant", seed_rbac_grants_entry)
    for op, handler in handlers.items():
        if registry.resolve(op) is not None:
            continue
        registry.register(op, handler)
    return registry
