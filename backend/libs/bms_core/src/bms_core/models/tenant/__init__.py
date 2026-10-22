"""共享模型子包：租户与配置服务来源、跨服务共用的 ORM 模型（5 文件 / 5 表）。

- 数据所有权：表级归属见 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`——模型的代码位置
  **不改变归属**（如 `sys_tenant` 建在 tenant 服务平台库，`owner` 即 `tenant`）；
- 本子包模型经 `bms_core/db/migration.py::COMMON_MODEL_MODULES` 纳入各建表链的模型发现；
- 服务侧 models 包已删除（14_01 整包下沉，不留转发层）。
"""

from bms_core.core.concurrent import ConcurrentStableList

MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_core.models.tenant.tenant",
        "bms_core.models.tenant.tenant_database",
        "bms_core.models.tenant.tenant_module",
        "bms_core.models.tenant.tenant_quota",
        "bms_core.models.tenant.user_tenant",
    )
)
"""本子包模型模块清单（与目录内模块一一对应；供基座模型发现组合）。"""
