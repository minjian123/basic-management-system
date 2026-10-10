"""api 聚合路由：平台地基 / 配置路由经服务级登记表统一挂到 `/api/v1`。

探针路由（`/healthz` `/readyz`）由共享应用基座统一挂载，不在此处登记。
"""

from bms_core.api.base import mount_service_routers
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.transaction.api import build_branch_router
from bms_platform.api import (
    account_locks,
    codecheck,
    demo,
    icon,
    internal_account_locks,
    internal_config,
    internal_credentials,
    internal_users,
    menu,
    modules,
    outbox,
    permission,
    plugins,
    preference,
    products,
    query_scheme,
    role,
    user_extensions,
    users,
)
from bms_platform.api import dict as dict_api

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            demo.router,
            modules.router,
            products.router,
            plugins.router,
            preference.router,
            query_scheme.router,
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
            account_locks.router,
            role.router,
            users.router,
            menu.menu_router,
            menu.form_router,
            menu.button_router,
            menu.field_router,
            menu.business_router,
            menu.action_router,
            menu.permission_router,
            # 跨服务事务参与端点（`/txn/branches*`；谁挂端点谁参与，05_07）
            build_branch_router(),
        ]
    )
)
