"""平台地基服务入口：应用工厂 `ApplicationFactory`（共享基座 + 平台身份 / 路由 + demo 注入）。

- 通用装配（中间件 / 异常处理 / 引擎与租户源 / 插件装配 / 探针 / lifespan）由共享基座
  `bms_core.application.BaseServiceApplicationFactory` 承载，本服务只声明身份、业务路由与 demo 注入。
- 启动入口见 `bms_platform/asgi.py`（`uvicorn bms_platform.asgi:app`）与 `python -m bms_platform`。
"""

from typing import cast

from fastapi import APIRouter, FastAPI

from bms_core.application import BaseServiceApplicationFactory, StartupHook
from bms_core.catalog.loader import register_catalog_reader
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db.registry import EngineRegistry
from bms_core.dict.outlet import register_data_source
from bms_core.permission.rbac import RBAC_PROVIDER_NAME
from bms_core.scope.rbac import RBAC_DATA_SCOPE_NAME, register_rbac_data_scope
from bms_platform import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_platform.api.router import api_router
from bms_platform.domains.permission_meta.icon.registry import (  # noqa: F401  (导入即登记 icon_registry:db)
    DB_ICON_PROVIDER,
    DbIconRegistry,  # pyright: ignore[reportUnusedImport]
)
from bms_platform.domains.permission_meta.permission.checker import register_platform_permission
from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
    bootstrap_capability_grants,
)
from bms_platform.domains.platform_registry.services.declaration_bootstrap import (
    bootstrap_platform_declarations,
)
from bms_platform.domains.platform_registry.services.tenant_topology_bootstrap import (
    bootstrap_tenant_topologies,
)
from bms_platform.domains.platform_registry.sources.catalog_source import read_catalog
from bms_platform.domains.platform_registry.sources.dict_source import PlatformDictDataSource
from bms_platform.repositories.demo_repository import DemoRepository
from bms_platform.services.branch_handlers import build_branch_handlers
from bms_platform.services.demo_service import DemoService


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：平台地基 / 配置服务（服务目录 / 插件 / 配置类路由 + demo 五层样板）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def prepare_settings(self, settings: Settings) -> None:
        """启用真实权限校验与数据范围（`04_01` 下沉后：实现随基座分发，本服务只注入数据来源）。

        `[permission].provider` / `[data_scope].provider` 未显式配置时置为 `rbac`；显式配置（含 `null`）
        一律尊重——便于联调期临时回退占位实现。

        登记放在本钩子而非 `configure_service`：插件注册表在应用构造中段即构建并冻结，而
        `configure_service` 晚于该时点（会报「运行期只读」）；本钩子是服务侧**建表前**唯一早期钩子。

        Args:
            settings: 应用配置（可变）。
        """
        if not settings.permission.provider:
            settings.permission.provider = RBAC_PROVIDER_NAME
        if not settings.data_scope.provider:
            settings.data_scope.provider = RBAC_DATA_SCOPE_NAME
        if not settings.icon_registry.provider:
            settings.icon_registry.provider = DB_ICON_PROVIDER
        # 平台侧装配：真实校验器 + 直查本库数据来源工厂 + 字段权限 provider 工厂
        register_platform_permission(settings)
        register_rbac_data_scope(settings)

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """平台业务路由。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由（探针由基座统一挂载）。
        """
        return ConcurrentStableList([api_router])

    def startup_hooks(self) -> ConcurrentStableList[StartupHook]:
        """启动钩子：平台自身声明注册（`02_06`）→ 能力分配声明同步 + 授权视图来源登记 + 预热（`02_04`）
        → 租户拓扑自举与第二段解析登记（07C `02_01`）。

        顺序不可颠倒：授权基线与入站判定都从**注册表派生的视图**取能力，声明必须先落；拓扑自举读的是
        同一份域登记视图，故排在声明之后。

        Returns:
            ConcurrentStableList[StartupHook]: 启动钩子清单。
        """
        return ConcurrentStableList(
            (bootstrap_platform_declarations, bootstrap_capability_grants, bootstrap_tenant_topologies)
        )

    def configure_service(self, app: FastAPI, settings: Settings) -> None:
        """注入平台专属 state（demo 服务）并登记本地权威读取器（服务目录）与权限实现。

        Args:
            app: 应用实例。
            settings: 应用配置（权限选项：档位 / 快照 TTL / 豁免角色类型）。
        """
        app.state.demo_service = DemoService(DemoRepository())
        # 分支业务处理器注册表（`op` → 本服务已有服务层方法；用户保存编排 op 于 `02_02/_02` 登记）
        app.state.branch_handlers = build_branch_handlers(app)
        # 服务目录权威本地读取器（本服务即 `sys_module` 所有者；共享基座库不静态依赖服务包）
        register_catalog_reader(SERVICE_NAME, read_catalog)
        # 字典平台内建数据源提供者（02_09：`sys_role` 等平台字典经统一出口取数；产品来源由前端直取）
        register_data_source(PlatformDictDataSource(engines=cast(EngineRegistry, app.state.engine_registry)))
