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
from bms_platform.domains.platform_registry.api import data_source, modules, products
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
            # 跨服务事务参与端点（`/txn/branches*`；谁挂端点谁参与，05_07）
            build_branch_router(),
        ]
    )
)
