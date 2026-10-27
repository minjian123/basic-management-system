"""平台服务 **种子分支处理器**（07B `02_03`）：把 9 个种子入口挂进 XA 分支注册表。

与 `branch_handlers.py`（用户 / 角色保存编排）同构：`op` → 本服务已有实现，
由基座分支执行器在**已开启的两阶段分支事务**的连接上调用。

**为什么单独一个模块**：种子分支是「运维初始化」用途，与业务编排（用户保存 / 角色保存）
职责不同；分文件便于按需注册与排障定位。
"""

from typing import cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.tenant.seed.platform import (
    seed_platform_grants_entry,
    seed_platform_roles_entry,
)
from bms_core.tenant.seed.rbac import seed_rbac_grants_entry, seed_rbac_roles_entry
from bms_core.transaction.base import BranchHandler, BranchHandlerRegistry

__all__ = ["SEED_OPS", "register_seed_handlers", "register_seed_stats"]

SEED_OPS: ConcurrentStableList[str] = ConcurrentStableList(
    (
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

    # 种子入口签名统一为 `async def entry(session, args) -> None`（详设 §3.9），与 BranchHandler 一致
    handlers: ConcurrentStableDict[str, BranchHandler] = ConcurrentStableDict()
    handlers.set("seed-module", cast("BranchHandler", seed_modules_entry))
    handlers.set("seed-tables", cast("BranchHandler", seed_tables_entry))
    handlers.set("seed-menu", cast("BranchHandler", seed_menu_entry))
    handlers.set("seed-tenant", cast("BranchHandler", seed_tenants_entry))
    handlers.set("seed-config", cast("BranchHandler", seed_configs_entry))
    handlers.set("seed-platform-role", cast("BranchHandler", seed_platform_roles_entry))
    handlers.set("seed-platform-grant", cast("BranchHandler", seed_platform_grants_entry))
    handlers.set("seed-rbac-role", cast("BranchHandler", seed_rbac_roles_entry))
    handlers.set("seed-rbac-grant", cast("BranchHandler", seed_rbac_grants_entry))
    for op, handler in handlers.items():
        if registry.resolve(op) is not None:
            continue
        registry.register(op, handler)
    return registry


def register_seed_stats(participant: object) -> None:
    """把种子统计探针登记进事务参与方（详设 §3.10：分支内采集逐项统计）。

    Args:
        participant: 事务参与方（须具备 `register_stats_probe`；占位实现无此方法时静默跳过）。
    """
    from bms_core.tenant.seed.probe import register_seed_probes

    register_seed_probes(participant)
