"""数据源实现（本服务）：导入即向共享基座登记 `local` 实现（06_03 租户源 / 11_01 关系数据源）。"""

from bms_tenant.sources.membership import LocalTenantMembershipStore, register_local_tenant_membership_store
from bms_tenant.sources.tenant_source import LocalTenantSource, register_local_tenant_source

__all__ = [
    "LocalTenantMembershipStore",
    "LocalTenantSource",
    "register_local_tenant_membership_store",
    "register_local_tenant_source",
]
