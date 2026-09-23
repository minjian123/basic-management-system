"""租户与配置服务路由聚合：模块路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
服务级登记表（`mount_service_routers`）避免多服务同进程登记串扰。
"""

from bms_core.api.base import mount_service_routers
from bms_tenant.api import tenant, tenant_registry

api_router = mount_service_routers((tenant.router, tenant_registry.router))
