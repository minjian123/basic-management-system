"""ops 入口的 WorkerId 租约引导（03_06 / 需求 03-7）。

`ops` 脚本属**短命进程**，同样会生成雪花 ID（seed / migrate / 一次性导入写库时）——统一在入口取号：
用完即释放，不长期占号。两种形态：

- 异步入口：``return run_with_worker_id(lambda: run(args))``（内部 `async with worker_id_lease()`）；
- 同步入口：``with worker_id_lease_sync(): ...``。

排除清单（`EXCLUDED_MODULES`）只容纳**不生成雪花 ID 的只读 / CI 校验工具**与 `dev_run`（其租约由
服务应用 lifespan 获得），判据由 `tests/ops/test_ops_worker_bootstrap.py` 固化：新增入口若调用
`asyncio.run` 却未进两份清单，护栏即失败。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from bms_core.core.concurrent import ConcurrentStableFrozenSet
from bms_core.workerid.lease import worker_id_lease, worker_id_lease_sync

__all__ = [
    "BOOTSTRAPPED_MODULES",
    "EXCLUDED_MODULES",
    "run_with_worker_id",
    "worker_id_lease_sync",
]

BOOTSTRAPPED_MODULES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    {
        "ops.baseline_series",
        "ops.bootstrap_platform",
        "ops.db_admin",
        "ops.event_consumer",
        "ops.init_schema",
        "ops.init_tenant",
        "ops.job_worker",
        "ops.migrate_tenants",
        "ops.migrate_topology",
        "ops.outbox",
        "ops.provision_tenant",
        "ops.release",
        "ops.seed_config",
        "ops.seed_menu",
        "ops.seed_module",
        "ops.seed_oidc_client",
        "ops.seed_platform",
        "ops.seed_rbac",
        "ops.seed_sso",
        "ops.seed_tables",
        "ops.seed_tenant",
        "ops.seed_user",
        "ops.task_scheduler",
        "ops.tenant_provisioning",
        "ops.tenant_topology",
        "ops.txn_recovery",
    }
)
"""已接入租约引导的 ops 入口（模块名口径）。"""

EXCLUDED_MODULES: ConcurrentStableFrozenSet[str] = ConcurrentStableFrozenSet(
    {
        "ops.check_budget",
        "ops.check_contracts",
        "ops.check_modules",
        "ops.check_plugins",
        "ops.check_tables",
        "ops.contract_gate",
        "ops.contract_snapshot",
        "ops.contract_smoke",
        "ops.dev_run",
        "ops.event_contracts",
        "ops.export_errcodes",
        "ops.gateway_config",
        "ops.test_db",
    }
)
"""有意不接的 ops 入口：只读 / CI 校验工具（不生成雪花 ID，且要能在无 Redis 的离线环境运行，
接入会污染机器可读输出）与 `dev_run`（经 runpy 进服务入口，租约由 lifespan 获得）。"""


def run_with_worker_id[T](entry: Callable[[], Awaitable[T]]) -> T:
    """在租约上下文内执行异步入口（取号 → 就绪校验 → 释放）。

    Args:
        entry: 无参异步可调用（通常为 `lambda: run(args)`）。

    Returns:
        _T: 入口返回值（退出码 / 查询结果）。
    """

    async def _runner() -> T:
        async with worker_id_lease():
            return await entry()

    return asyncio.run(_runner())
