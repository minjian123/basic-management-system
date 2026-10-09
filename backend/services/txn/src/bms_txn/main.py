"""跨服务事务管理器服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由）。"""

from fastapi import APIRouter, FastAPI

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_txn import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_txn.api.router import api_router
from bms_txn.services.driver import BranchDriver, UnavailableBranchDriver


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：跨服务事务管理器服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def prepare_settings(self, settings: Settings) -> None:
        """就绪探针缺省回退空注册表（**不启用**外部依赖检查）。

        生产 / 联调经 `[health_check_registry].provider = "local"` 显式启用（数据库等检查）；
        缺省空注册表使本地与冒烟环境免外部依赖（口径同服务脚手架）。

        Args:
            settings: 应用配置（可变）。
        """
        if not settings.health_check_registry.provider:
            settings.health_check_registry.provider = ""

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由。
        """
        return ConcurrentStableList([api_router])

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """装配分支驱动（参与端点未接入期间为**明确失败**实现；接入后换 HTTP 驱动）。

        Args:
            app: 应用实例。
            settings: 应用配置（TM 协调参数）。
        """
        app.state.branch_driver = _initial_driver()


def _initial_driver() -> BranchDriver:
    """初始分支驱动：参与端点尚未接入 ⇒ `UnavailableBranchDriver`（明确失败、不静默成功）。

    Returns:
        BranchDriver: 分支驱动实现。
    """
    return UnavailableBranchDriver()
