"""共享模型子包：平台服务来源、按业务域一文件一模块。

- 数据所有权：表级归属见 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`——模型的代码位置
  **不改变归属**（表建在哪个服务的库，`owner` 就是哪个服务）；
- 本清单是「本子包有哪些模型模块」的**全量清单**（无域布局时的安全回退面）；业务域的精确模型模块
  由 `deploy/boundaries/domain_layout.json` 派生（`db/migration.py::domain_model_modules`）；
- 服务侧 models 包已删除（14_01 整包下沉，不留转发层）；文件级混域已在 07C `03_03` 拆开。
"""

from bms_core.core.concurrent import ConcurrentStableList

MODEL_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_core.models.platform.capability_grant",
        "bms_core.models.platform.catalog",
        "bms_core.models.platform.demo",
        "bms_core.models.platform.icon",
        "bms_core.models.platform.menu_form",
        "bms_core.models.platform.permission_meta",
        "bms_core.models.platform.role",
        "bms_core.models.platform.task",
        "bms_core.models.platform.user",
    )
)
"""本子包模型模块清单（与目录内模块一一对应；供基座模型发现组合）。"""
