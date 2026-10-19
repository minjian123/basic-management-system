"""认证与身份服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由）。

`04_01` 下沉后本服务接入真实权限校验：`prepare_settings` 里置 `[permission].provider = rbac` 并登记
「经 platform 内部只读契约取数」的数据来源——此前 `require_permission` 解析到基座占位实现（恒放行）。
"""

from fastapi import APIRouter

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.permission.rbac import RBAC_PROVIDER_NAME
from bms_identity import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_identity.api.router import api_router
from bms_identity.api.wellknown import router as wellknown_router
from bms_identity.permission import register_identity_permission


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：认证与身份服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def prepare_settings(self, settings: Settings) -> None:
        """启用真实权限校验（`04_01`：实现随基座分发，本服务只注入数据来源）。

        `[permission].provider` 未显式配置时置为 `rbac`；显式配置（含 `null`）一律尊重。
        `data_scope` 保持占位：identity 无数据范围消费面（不注入数据范围来源）。

        登记放在本钩子而非 `configure_service`：插件注册表在应用构造中段即构建并冻结，而
        `configure_service` 晚于该时点（会报「运行期只读」）。

        Args:
            settings: 应用配置（可变）。
        """
        if not settings.permission.provider:
            settings.permission.provider = RBAC_PROVIDER_NAME
        register_identity_permission(settings)

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由 + JWKS 公开端点（`/.well-known/jwks.json`）。
        """
        return ConcurrentStableList([api_router, wellknown_router])
