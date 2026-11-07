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
from bms_platform.domains.i18n.api import locales as i18n_locales
from bms_platform.domains.i18n.api import messages as i18n_messages
from bms_platform.domains.import_export.api.exports import build_export_router
from bms_platform.domains.import_export.api.imports import build_import_router
from bms_platform.domains.job.api import internal_job as internal_job_api
from bms_platform.domains.job.api import job as job_api
from bms_platform.domains.log.api import internal_audit as internal_audit_api
from bms_platform.domains.log.api.logs import login_router as login_log_api
from bms_platform.domains.log.api.logs import router as operation_log_api
from bms_platform.domains.menu_form.api import form_key, menu
from bms_platform.domains.permission_meta.api import icon, permission, permission_meta
from bms_platform.domains.platform_config.api import configs, internal_config, query_scheme
from bms_platform.domains.platform_registry.api import (
    capability_grants,
    data_source,
    internal_capability_grants,
    internal_declarations,
    internal_seeds,
    internal_tenant_topologies,
    modules,
    products,
    releases,
    scope_resources,
    tenant_quotas,
    tenant_topologies,
)
from bms_platform.domains.platform_registry.api import dict as dict_api
from bms_platform.domains.role.api import role
from bms_platform.domains.task.api import task as task_api
from bms_platform.domains.user.api import (
    account_locks,
    internal_account_locks,
    internal_credentials,
    internal_users,
    preference,
    profile,
    user_extensions,
    users,
)
from bms_platform.exports import build_export_definitions
from bms_platform.imports import build_import_definitions
from bms_platform.jobs import build_runner

api_router = mount_service_routers(
    ConcurrentStableList(
        [
            demo.router,
            modules.router,
            products.router,
            plugins.router,
            preference.router,
            profile.router,
            query_scheme.router,
            data_source.router,
            form_key.router,
            dict_api.router,
            icon.router,
            codecheck.router,
            outbox.router,
            internal_config.router,
            # 系统参数管理面（02_02）：分页 / 详情 / 新增 / 修改 / 重置 / 删除 / 恢复
            configs.router,
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
            # 作用域资源类型运营面（07D `01_01`）：查询 + 运营期停用 / 恢复
            scope_resources.router,
            # 租户配额只读视图（07D `02_03`）：产品配额投影，平台只读、不双写
            tenant_quotas.router,
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
            # 发布清单（07C `04_01`）：只读管理面（发布与回滚是部署编排动作，经 `ops.release`）
            releases.router,
            # 任务调度（01_02）：任务定义 / 启停 / 手动触发 / 执行记录
            task_api.router,
            # 异步作业中心（01_03）：类型目录 / 统一列表 / 详情 / 取消 / 重试 + 服务内部面
            job_api.router,
            internal_job_api.router,
            # 跨服务事务参与端点（`/txn/branches*`；谁挂端点谁参与，05_07）
            build_branch_router(),
            # Excel 批量导入（04_01）：模板 / 执行 / 异步状态 / 错误明细
            build_import_router(
                definitions_factory=build_import_definitions,
                runner_factory=build_runner,
            ),
            # 列表导出（04_02）：Excel / 列表 PDF / 异步作业状态
            build_export_router(
                definitions_factory=build_export_definitions,
                runner_factory=build_runner,
            ),
            # 国际化（05_01）：语言清单维护 + 语言包下发 / 维护 / 缓存失效
            i18n_locales.router,
            i18n_messages.router,
            # 审计日志（06_01）：操作 / 登录日志查询 + 链校验 / 分片预创建内部面
            operation_log_api,
            login_log_api,
            internal_audit_api.router,
        ]
    )
)
