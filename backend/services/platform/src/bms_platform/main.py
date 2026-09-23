"""平台地基服务入口：应用工厂 `ApplicationFactory`（共享基座 + 平台身份 / 路由 + demo 注入）。

- 通用装配（中间件 / 异常处理 / 引擎与租户源 / 插件装配 / 探针 / lifespan）由共享基座
  `bms_core.application.BaseServiceApplicationFactory` 承载，本服务只声明身份、业务路由与 demo 注入。
- 启动入口见 `bms_platform/asgi.py`（`uvicorn bms_platform.asgi:app`）与 `python -m bms_platform`。
"""

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI

from bms_core.application import BaseServiceApplicationFactory
from bms_core.catalog.loader import register_catalog_reader
from bms_core.core.config import Settings
from bms_platform import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_platform.api.router import api_router
from bms_platform.repositories.demo_repository import DemoRepository
from bms_platform.services.demo_service import DemoService
from bms_platform.sources.catalog_source import read_catalog


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：平台地基 / 配置服务（服务目录 / 插件 / 配置类路由 + demo 五层样板）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def service_routers(self) -> Sequence[APIRouter]:
        """平台业务路由。

        Returns:
            Sequence[APIRouter]: 业务聚合路由（探针由基座统一挂载）。
        """
        return (api_router,)

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """注入平台专属 state（demo 服务）并登记本地权威读取器（服务目录）。

        Args:
            app: 应用实例。
            settings: 应用配置（未使用）。
        """
        del settings
        app.state.demo_service = DemoService(DemoRepository())
        # 服务目录权威本地读取器（本服务即 `sys_module` 所有者；共享基座库不静态依赖服务包）
        register_catalog_reader(SERVICE_NAME, read_catalog)
