"""租户与配置服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由）。"""

from fastapi import APIRouter

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.tenant.base import TENANT_SELF_SERVICE_DB_PROVIDER
from bms_tenant import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_tenant.api.router import api_router
from bms_tenant.sources import register_local_tenant_membership_store, register_local_tenant_source

register_local_tenant_source()  # 向共享基座登记 `local` 租户源实现（本服务直读自身平台服务库）
register_local_tenant_membership_store()  # 登记 `local` 关系数据源实现（11_01）


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：租户与配置服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def prepare_settings(self, settings: Settings) -> None:
        """本服务配置调整：承载租户自助真实实现（provider 选 `sql`；其余服务保持占位）。

        Args:
            settings: 应用配置（可变）。
        """
        if self.service_name == SERVICE_NAME:
            settings.tenant_self_service.provider = TENANT_SELF_SERVICE_DB_PROVIDER

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由。
        """
        return ConcurrentStableList([api_router])
