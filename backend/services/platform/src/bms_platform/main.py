"""平台地基服务入口：应用工厂 `ApplicationFactory`（共享基座 + 平台身份 / 路由 + demo 注入）。

- 通用装配（中间件 / 异常处理 / 引擎与租户源 / 插件装配 / 探针 / lifespan）由共享基座
  `bms_core.application.BaseServiceApplicationFactory` 承载，本服务只声明身份、业务路由与 demo 注入。
- 启动入口见 `bms_platform/asgi.py`（`uvicorn bms_platform.asgi:app`）与 `python -m bms_platform`。
"""

from fastapi import APIRouter, FastAPI

from bms_core.application import BaseServiceApplicationFactory
from bms_core.catalog.loader import register_catalog_reader
from bms_core.core.concurrent import ConcurrentStableList
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

    # 说明（`02_04`）：真实权限校验器（`rbac`）的实现登记与 `[permission].provider` 切换需在
    # **插件注册表构建之前**完成——服务侧唯一早期钩子是 `prepare_settings()`（`configure_service`
    # 已晚于注册表冻结）。激活动作与既有「默认装配为 null 实现」用例集的同步更新一并进行，
    # 见 `02_04` 实施记录「剩余工作」。

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """平台业务路由。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由（探针由基座统一挂载）。
        """
        return ConcurrentStableList([api_router])

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """注入平台专属 state（demo 服务）并登记本地权威读取器（服务目录）与权限实现。

        Args:
            app: 应用实例。
            settings: 应用配置（权限选项：档位 / 快照 TTL / 豁免角色类型）。
        """
        app.state.demo_service = DemoService(DemoRepository())
        # 服务目录权威本地读取器（本服务即 `sys_module` 所有者；共享基座库不静态依赖服务包）
        register_catalog_reader(SERVICE_NAME, read_catalog)
