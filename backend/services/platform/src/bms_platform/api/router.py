"""api 聚合路由：平台地基 / 配置路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
"""

from bms_core.api.base import mount_service_routers
from bms_platform.api import codecheck, demo, icon, modules, plugins, preference, query_scheme
from bms_platform.api import dict as dict_api

api_router = mount_service_routers(
    (
        demo.router,
        modules.router,
        plugins.router,
        preference.router,
        query_scheme.router,
        dict_api.router,
        icon.router,
        codecheck.router,
    )
)
