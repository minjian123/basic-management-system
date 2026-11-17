"""表单定制域只读 DTO（跨域出口用；不可变数据类，落 `BaseValueObject`）。"""

from dataclasses import dataclass, field

from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.core.objects import BaseValueObject

__all__ = [
    "EffectiveLayoutView",
    "ExtFieldSummary",
    "FieldSpec",
    "ImportColumn",
]


@dataclass(frozen=True)
class FieldSpec(BaseValueObject):
    """合并字段清单项（平台字段 + 自建字段）。"""

    key: str
    """字段键。"""
    label: str
    """字段名（当前 locale）。"""
    type: str
    """字段类型。"""
    group: str = "platform"
    """来源分组（`platform` / `tenant`）。"""
    sort: int = 0
    """同表单内排序（升序）。"""
    status: str = "active"
    """状态（`active` / `pending` / `failed` / `disabled`）。"""
    disabled: bool = False
    """是否不可拖入（停用 / 建列失败）。"""
    attrs: ConcurrentStableFrozenDict[str, object] = field(default_factory=lambda: ConcurrentStableFrozenDict({}))
    """生效字段属性（`attrs` 归一后的字典）。"""
    permission: ConcurrentStableFrozenDict[str, object] | None = None
    """字段权限收窄项（`visible` / `editable` / `required`）；None 表示全开。"""


@dataclass(frozen=True)
class EffectiveLayoutView(BaseValueObject):
    """生效布局视图（渲染路径组装结果；与前端 `LayoutEffective` 同形）。"""

    layout: ConcurrentStableFrozenDict[str, object]
    """生效布局配置（`layout_config` 结构）。"""
    fields: ConcurrentStableFrozenList[FieldSpec]
    """合并字段清单（已按权限剔除不可见字段）。"""
    level: str
    """请求层级。"""
    source: str
    """实际来源层级（`role` / `tenant` / `platform` / `empty`）。"""
    fallback: bool
    """是否走了空布局回退。"""
    option_sets: ConcurrentStableFrozenList[ConcurrentStableFrozenDict[str, object]] = field(
        default_factory=lambda: ConcurrentStableFrozenList(())
    )
    """选项集快照集（`{optionSetKey, items[]}`）。"""
    permissions: ConcurrentStableFrozenDict[str, ConcurrentStableFrozenDict[str, object]] = field(
        default_factory=lambda: ConcurrentStableFrozenDict({})
    )
    """字段权限标记（仅收窄项）。"""


@dataclass(frozen=True)
class ExtFieldSummary(BaseValueObject):
    """自建字段摘要（跨域读用）。"""

    field_key: str
    """字段键。"""
    name: str
    """字段名（当前 locale）。"""
    type: str
    """字段类型。"""
    column_name: str
    """物理列名。"""
    ddl_status: str
    """建列生命周期。"""
    status: str
    """启用状态。"""
    option_set_key: str | None = None
    """选项集标识。"""


@dataclass(frozen=True)
class ImportColumn(BaseValueObject):
    """导入列（跨域读用；`users` 导入定义派生列集时经本 DTO 消费）。"""

    key: str
    """字段键。"""
    title: str
    """列标题（当前 locale）。"""
    required: bool = False
    """是否必填。"""
    max_length: int | None = None
    """文本最大长度（None 不限）。"""
    value_type: str = "text"
    """通用读值类型。"""
    choices: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList(()))
    """可选值（枚举字段）。"""
