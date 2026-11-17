"""生效布局与动态校验请求 / 响应模型（`/forms/{form_code}/layout-effective`）。"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
)

__all__ = [
    "EffectiveField",
    "EffectiveFieldPermission",
    "FormValidateRequest",
    "FormValidateResponse",
    "LayoutEffectiveResponse",
    "OptionSetSnapshotModel",
    "ValidateFieldError",
]


class EffectiveFieldPermission(BaseSchema):
    """字段权限标记（仅收窄项）。"""

    visible: bool = Field(default=True, description="是否可见")
    editable: bool = Field(default=True, description="是否可编辑")


class EffectiveField(BaseSchema):
    """合并字段清单项（已剔除不可见字段）。"""

    key: str = Field(description="字段键")
    label: str = Field(description="字段名（当前 locale）")
    type: str = Field(description="字段类型")
    group: str = Field(description="来源分组（platform / tenant）")
    sort: int = Field(description="排序")
    status: str = Field(description="状态（active / pending / failed / disabled）")
    disabled: bool = Field(default=False, description="是否不可拖入（停用 / 建列失败）")
    attrs: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="生效字段属性"
    )


class OptionSetSnapshotModel(BaseSchema):
    """选项集快照（随渲染元数据下发，前端零请求消费）。"""

    option_set_key: str = Field(description="选项集标识")
    items: Annotated[ConcurrentStableList[ConcurrentStableDict[str, object]], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="条目（value / label / color / disabled / sort）"
    )


class LayoutEffectiveResponse(BaseSchema):
    """生效布局响应（与前端 `LayoutEffective` 同形）。"""

    layout: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="生效布局配置"
    )
    fields: Annotated[ConcurrentStableList[EffectiveField], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="合并字段清单（已按权限剔除）"
    )
    level: str = Field(description="请求层级")
    source: str = Field(description="实际来源层级（role / tenant / platform / empty）")
    readonly: bool = Field(default=True, description="是否只读（渲染路径恒 true）")
    fallback: bool = Field(description="是否走空布局回退")
    option_sets: Annotated[ConcurrentStableList[OptionSetSnapshotModel], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="选项集快照集"
    )
    permissions: Annotated[ConcurrentStableDict[str, EffectiveFieldPermission], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="字段权限标记（仅收窄项）"
    )


class FormValidateRequest(BaseSchema):
    """动态校验自测请求。"""

    values: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="字段键 → 待校验值"
    )


class ValidateFieldError(BaseSchema):
    """字段级校验错误。"""

    field_key: str = Field(description="字段键")
    rule: str = Field(description="规则种类（required / length / range / pattern / options / type）")
    message: str | None = Field(default=None, description="后端补充说明（通常为空，前端按 rule 取词）")


class FormValidateResponse(BaseSchema):
    """动态校验响应。"""

    valid: bool = Field(description="是否通过")
    errors: Annotated[ConcurrentStableList[ValidateFieldError], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="字段级错误（通过时为空）"
    )


del ConcurrentStableFrozenList
