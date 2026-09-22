"""AI服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由）。"""

from collections.abc import Sequence

from fastapi import APIRouter

from bms_ai import SERVICE_NAME, SERVICE_TITLE, __version__
from bms_ai.api.router import api_router
from bms_core.application import BaseServiceApplicationFactory


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：AI服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__

    def service_routers(self) -> Sequence[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            Sequence[APIRouter]: 业务聚合路由。
        """
        return (api_router,)
