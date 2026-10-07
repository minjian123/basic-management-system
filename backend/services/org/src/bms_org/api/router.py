"""组织主数据服务路由聚合：模块路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
服务级登记表（`mount_service_routers`）避免多服务同进程登记串扰。

本服务当前只挂**组织主数据占位路由**（`/org/users` `/org/posts` `/org/dept-tree`
`/org/resolve-names`，经组织数据源契约消费）；用户（系统账号）与账号锁定端点随需求 07-10
归口 platform 服务（原 `/org/internal/credentials/*`、`/org/internal/users/*`、
`/org/internal/account-locks/*`、`/org/locks` 已迁出）。
"""

from bms_core.api.base import mount_service_routers
from bms_core.core.concurrent import ConcurrentStableList
from bms_org.api import org

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            org.router,
        ]
    )
)
