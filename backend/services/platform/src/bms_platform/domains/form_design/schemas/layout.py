"""布局与字段属性请求 / 响应模型（`/form-design/layouts` / `/form-design/attrs`）。

集合字段一律插入序集合类 + `CONTRACT_COLLECTION` 注解（不用裸 `list` / `dict`）；主键按
`SnowflakeIdStr` 字符串化（JS 安全整数）。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    BaseSchema,
    SnowflakeIdStr,
)

__all__ = [
    "FieldAttrItem",
    "FieldAttrRow",
    "FieldAttrSaveRequest",
    "LayoutLevelRow",
    "LayoutListResponse",
    "LayoutSaveRequest",
    "LayoutSaveResult",
    "LayoutWarning",
]


class FieldAttrItem(BaseSchema):
    """单字段属性项（保存请求项）。"""

    field_key: str = Field(min_length=1, max_length=64, description="字段键")
    field_type: str = Field(min_length=1, max_length=32, description="字段类型（枚举类型必配选项集）")
    attrs: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT,
        description="字段属性（required / placeholder / defaultValue / rules / optionSetKey / widget / readonly 等）",
    )


class LayoutSaveRequest(BaseSchema):
    """保存层级布局请求（整份覆盖式；裸字符串引用与对象引用都接受）。"""

    form_code: str = Field(min_length=1, max_length=64, description="表单标识（业务码）")
    scope: str = Field(min_length=1, max_length=16, description="层级（platform / tenant / role）")
    role_id: SnowflakeIdStr = Field(default="0", description="角色 ID（role 层级必填；其余层级固定 0）")
    layout_config: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT,
        description="布局配置（main + query + detail + dictAdvanced）",
    )


class FieldAttrSaveRequest(BaseSchema):
    """保存层级字段属性请求（整份覆盖式）。"""

    form_code: str = Field(min_length=1, max_length=64, description="表单标识（业务码）")
    scope: str = Field(min_length=1, max_length=16, description="层级（platform / tenant / role）")
    role_id: SnowflakeIdStr = Field(default="0", description="角色 ID（role 层级必填；其余层级固定 0）")
    fields: Annotated[ConcurrentStableList[FieldAttrItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST,
        description="字段属性清单（整份覆盖；空列表表示清空该层属性）",
    )


class LayoutLevelRow(BaseSchema):
    """层级布局行（列表响应项）。"""

    id: SnowflakeIdStr = Field(description="布局主键")
    form_code: str = Field(description="表单标识")
    scope: str = Field(description="层级")
    role_id: SnowflakeIdStr = Field(description="角色 ID（0 表示非角色层级）")
    layout_config: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="布局配置（归一后）"
    )
    status: str = Field(description="状态")


class FieldAttrRow(BaseSchema):
    """层级字段属性行（列表响应项）。"""

    id: SnowflakeIdStr = Field(description="属性主键")
    form_code: str = Field(description="表单标识")
    scope: str = Field(description="层级")
    role_id: SnowflakeIdStr = Field(description="角色 ID")
    field_key: str = Field(description="字段键")
    attrs: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="字段属性（归一后）"
    )


class LayoutWarning(BaseSchema):
    """布局引用告警（失效 / 停用 / 重复；保存期告警不阻断）。"""

    kind: str = Field(description="问题种类（unknown-field / disabled-field / duplicate-field / empty-section）")
    field_key: str | None = Field(default=None, description="涉事字段键")
    section_key: str | None = Field(default=None, description="涉事分区键")
    message: str = Field(default="", description="说明")


class LayoutSaveResult(BaseSchema):
    """布局 / 属性保存结果。"""

    id: SnowflakeIdStr = Field(description="主键（属性整份保存时取层级首个属性行；空层级为 0）")
    scope: str = Field(description="层级")
    role_id: SnowflakeIdStr = Field(description="角色 ID")
    applied: bool = Field(description="是否已生效（缓存已失效）")
    warnings: Annotated[ConcurrentStableList[LayoutWarning], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="布局引用告警（不阻断保存）"
    )


class LayoutListResponse(BaseSchema):
    """三层布局 + 三层属性清单。"""

    layouts: Annotated[ConcurrentStableList[LayoutLevelRow], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="布局行清单"
    )
    attrs: Annotated[ConcurrentStableList[FieldAttrRow], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="属性行清单"
    )
    warnings: Annotated[ConcurrentStableList[LayoutWarning], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="失效 / 停用 / 重复引用告警（不阻断）"
    )
    levels: Annotated[ConcurrentStableList[str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="已配置层级（platform / tenant / role；空表示走默认栅格）"
    )
