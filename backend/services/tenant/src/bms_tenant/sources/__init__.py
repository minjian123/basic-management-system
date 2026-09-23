"""租户源实现（本服务）：导入即向共享基座登记 `local` 实现（06_03）。"""

from bms_tenant.sources.tenant_source import LocalTenantSource, register_local_tenant_source

__all__ = ["LocalTenantSource", "register_local_tenant_source"]
