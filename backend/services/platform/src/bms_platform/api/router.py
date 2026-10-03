"""api 聚合路由：平台地基 / 配置路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
"""

from bms_core.api.base import mount_service_routers
from bms_core.core.concurrent import ConcurrentStableList
from bms_platform.api import (
    codecheck,
    demo,
    icon,
    internal_config,
    modules,
    outbox,
    plugins,
    preference,
    query_scheme,
    user_extensions,
)
from bms_platform.api import dict as dict_api

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            demo.router,
            modules.router,
            plugins.router,
            preference.router,
            query_scheme.router,
            dict_api.router,
            icon.router,
            codecheck.router,
            outbox.router,
            internal_config.router,
            user_extensions.router,
        ]
    )
)
