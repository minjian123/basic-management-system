"""api 聚合路由：平台地基 / 配置路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
"""

from bms_core.api.base import mount_service_routers
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.transaction.api import build_branch_router
from bms_platform.api import (
    codecheck,
    demo,
    outbox,
    plugins,
)
from bms_platform.domains.menu_form.api import form_key, menu
from bms_platform.domains.permission_meta.api import icon, permission, permission_meta
from bms_platform.domains.platform_config.api import internal_config, query_scheme
from bms_platform.domains.platform_registry.api import (
    capability_grants,
    data_source,
    internal_capability_grants,
    internal_declarations,
    internal_seeds,
    internal_tenant_topologies,
    modules,
    products,
    tenant_topologies,
)
from bms_platform.domains.platform_registry.api import dict as dict_api
from bms_platform.domains.role.api import role
from bms_platform.domains.user.api import (
    account_locks,
    internal_account_locks,
    internal_credentials,
    internal_users,
    preference,
    user_extensions,
    users,
)

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            demo.router,
            modules.router,
            products.router,
            plugins.router,
            preference.router,
            query_scheme.router,
            data_source.router,
            form_key.router,
            dict_api.router,
            icon.router,
            codecheck.router,
            outbox.router,
            internal_config.router,
            user_extensions.router,
            internal_credentials.router,
            internal_users.router,
            internal_users.query_router,
            internal_account_locks.router,
            permission.router,
            permission.read_router,
            account_locks.router,
            role.router,
            users.router,
            menu.menu_router,
            menu.form_router,
            menu.button_router,
            menu.field_router,
            permission_meta.business_router,
            permission_meta.action_router,
            permission_meta.permission_router,
            # 能力分配授权（07B `02_04`）：管理面 + 内部授权视图（新增路由追加在末尾，契约快照仅追加）
            capability_grants.router,
            internal_capability_grants.router,
            # 产品声明注册通道（07B `02_06`）：产品启动时全量上报 + 消费方拉取快照
            internal_declarations.router,
            # 种子统一编排（07B `02_03`）：部署初始化时由 CLI 触发，平台进程内执行
            internal_seeds.router,
            # 租户部署拓扑（07C `02_01`）：管理面分页 / 导出 / 整批写入（运维与部署编排面）
            tenant_topologies.router,
            # 拓扑全量快照（07C `02_02`）：服务间读取，各进程装配期拉取后登记第二段解析
            internal_tenant_topologies.router,
            # 跨服务事务参与端点（`/txn/branches*`；谁挂端点谁参与，05_07）
            build_branch_router(),
        ]
    )
)
