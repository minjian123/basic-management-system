"""回收站表规格与引擎输出值对象（13_01）。

- **表规格**：`RecycleTableSpec` 描述「哪些表进回收站、怎么展示、怎么级联、是否可单独恢复」；
  平台首批规格在 `registry.py`，其他服务 / 产品经 `register_recycle_tables()` 追加。
- **值对象**：模块 / 表计数、列表行、详情、恢复结果、清理结果均为不可变数据类；
  集合字段一律落冻结形态 `ConcurrentStableFrozen*`（值对象语义）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.roots import BaseValueObject

__all__ = [
    "RecycleCascade",
    "RecycleDetail",
    "RecycleField",
    "RecycleModule",
    "RecyclePageRow",
    "RecyclePurgeOutcome",
    "RecycleRestoreOutcome",
    "RecycleTableInfo",
    "RecycleTableSpec",
]


@dataclass(frozen=True)
class RecycleField(BaseValueObject):
    """展示列（列名 + 中文标签）。"""

    column: str
    """物理列名。"""

    label: str
    """中文展示标签。"""


@dataclass(frozen=True)
class RecycleCascade(BaseValueObject):
    """级联恢复关系（子表 + 指向父行的列）。"""

    table: str
    """子表逻辑表名。"""

    column: str
    """子表中指向父行主键的列名。"""

    recursive: bool = False
    """是否按该列递归展开（仅自引用树表，如帮助分类 `parent_id`）。"""


@dataclass(frozen=True)
class RecycleTableSpec(BaseValueObject):
    """回收站表规格（注册与校验的唯一单元）。"""

    table: str
    """逻辑表名。"""

    label: str
    """中文表名。"""

    module_key: str
    """所属模块标识（业务域 / 功能分组）。"""

    module_label: str
    """所属模块中文名。"""

    title_field: str
    """列表标题列（展示主标识）。"""

    visible_fields: ConcurrentStableFrozenList[RecycleField] = field(
        default_factory=lambda: ConcurrentStableFrozenList(())
    )
    """详情展示列（白名单；不返回整行）。"""

    keyword_fields: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """关键字匹配列（仅字符串列）。"""

    cascades: ConcurrentStableFrozenList[RecycleCascade] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """级联恢复子表（按登记顺序恢复）。"""

    visible: bool = True
    """是否出现在模块 / 列表（隐藏子表只参与级联与清理）。"""

    restorable: bool = True
    """是否允许单独恢复（隐藏子表不可单独恢复）。"""


@dataclass(frozen=True)
class RecycleTableInfo(BaseValueObject):
    """模块内单表计数。"""

    table: str
    label: str
    deleted_count: int


@dataclass(frozen=True)
class RecycleModule(BaseValueObject):
    """模块分组（含表计数）。"""

    module_key: str
    module_label: str
    deleted_count: int
    tables: ConcurrentStableFrozenList[RecycleTableInfo]


@dataclass(frozen=True)
class RecyclePageRow(BaseValueObject):
    """软删除列表行（轻量：标题 + 删除信息）。"""

    table: str
    id: int
    title: str
    deleted_at: datetime
    deleted_by: int | None = None


@dataclass(frozen=True)
class RecycleDetail(BaseValueObject):
    """软删除详情（展示列快照）。"""

    table: str
    id: int
    title: str
    deleted_at: datetime
    deleted_by: int | None
    created_at: datetime
    updated_at: datetime
    fields: ConcurrentStableFrozenDict[str, str]


@dataclass(frozen=True)
class RecycleRestoreOutcome(BaseValueObject):
    """恢复结果（主行标题 / 旧删除时间 / 级联计数）。"""

    table: str
    id: int
    title: str
    old_deleted_at: datetime
    cascaded: ConcurrentStableFrozenDict[str, int]


@dataclass(frozen=True)
class RecyclePurgeOutcome(BaseValueObject):
    """单表清理结果。"""

    table: str
    deleted_count: int
    batches: int
