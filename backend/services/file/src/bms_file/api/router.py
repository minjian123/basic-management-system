"""文件服务路由聚合：模块路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
服务级登记表（`mount_service_routers`）避免多服务同进程登记串扰。
"""

from bms_core.api.base import mount_service_routers
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.jobs.api import build_job_internal_router
from bms_file.domains.file.api import file
from bms_file.jobs import build_runner

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            file.router,
            file.router_internal,
            build_job_internal_router(runner_factory=build_runner),
        ]
    )
)
