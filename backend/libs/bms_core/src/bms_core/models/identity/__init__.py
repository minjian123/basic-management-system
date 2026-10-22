"""共享模型子包：认证与身份服务来源、跨服务共用的 ORM 模型（4 文件 / 4 表）。

- 数据所有权：表级归属见 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`——模型的代码位置
  **不改变归属**（如 `sys_user_identity` 建在平台库，`owner` 即 `identity`）；
- 本子包模型经 `bms_core/db/migration.py::COMMON_MODEL_MODULES` 纳入各建表链的模型发现；
- 服务侧 models 包已删除（14_01 整包下沉，不留转发层）。
"""

from bms_core.core.concurrent import ConcurrentStableList

MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_core.models.identity.client",
        "bms_core.models.identity.identity_provider",
        "bms_core.models.identity.session",
        "bms_core.models.identity.user_identity",
    )
)
"""本子包模型模块清单（与目录内模块一一对应；供基座模型发现组合）。"""
