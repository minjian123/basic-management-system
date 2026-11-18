"""回收站通用能力（13_01）：表规格登记 + 查询 / 恢复 / 超期清理引擎。

- `registry.py`：平台首批 18 张表规格与追加注册口；
- `spec.py`：表规格与引擎输出值对象；
- `engine.py`：模块计数 / 单表分页 / 详情 / 恢复（唯一冲突 + 级联）/ 逐表清理。

其他服务 / 产品可复用本包：装载期登记自己的表规格，请求 / 作业内构造 `RecycleEngine`，
各自挂路由与作业；平台不跨库、不跨服务直写。
"""

from bms_core.recycle.engine import RecycleEngine, model_for_table
from bms_core.recycle.registry import (
    RECYCLE_TABLES,
    recycle_spec_of,
    recycle_table_specs,
    register_recycle_tables,
    reset_recycle_tables,
    validate_recycle_specs,
    visible_recycle_specs,
)
from bms_core.recycle.spec import (
    RecycleCascade,
    RecycleDetail,
    RecycleField,
    RecycleModule,
    RecyclePageRow,
    RecyclePurgeOutcome,
    RecycleRestoreOutcome,
    RecycleTableInfo,
    RecycleTableSpec,
)

__all__ = [
    "RECYCLE_TABLES",
    "RecycleCascade",
    "RecycleDetail",
    "RecycleEngine",
    "RecycleField",
    "RecycleModule",
    "RecyclePageRow",
    "RecyclePurgeOutcome",
    "RecycleRestoreOutcome",
    "RecycleTableInfo",
    "RecycleTableSpec",
    "model_for_table",
    "recycle_spec_of",
    "recycle_table_specs",
    "register_recycle_tables",
    "reset_recycle_tables",
    "validate_recycle_specs",
    "visible_recycle_specs",
]
