"""租户自建字段请求 / 响应模型（`/form-design/fields`）。"""

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
    "ExtFieldCreateRequest",
    "ExtFieldItem",
    "ExtFieldListResponse",
    "ExtFieldUpdateRequest",
]


class ExtFieldCreateRequest(BaseSchema):
    """新建自建字段（触发动态 DDL）。"""

    form_code: str = Field(min_length=1, max_length=64, description="表单标识（业务码）")
    field_key: str = Field(min_length=1, max_length=64, description="字段键（小写字母开头，仅小写 / 数字 / 下划线）")
    name: str = Field(min_length=1, max_length=128, description="字段名（默认文案）")
    type: str = Field(
        min_length=1,
        max_length=32,
        description="字段类型（text / longtext / number / datetime / option / option_multi / switch / file）",
    )
    option_set_key: str | None = Field(default=None, max_length=128, description="选项集标识（枚举类型必填）")
    sort: int = Field(default=0, description="同表单内排序（升序）")


class ExtFieldUpdateRequest(BaseSchema):
    """编辑自建字段（停用不删列）。"""

    name: str | None = Field(default=None, max_length=128, description="字段名（None 表示不改）")
    status: str | None = Field(default=None, max_length=16, description="状态（enabled / disabled）")
    option_set_key: str | None = Field(default=None, max_length=128, description="选项集标识（None 表示不改）")
    sort: int | None = Field(default=None, description="排序（None 表示不改）")


class ExtFieldItem(BaseSchema):
    """自建字段项（列表响应）。"""

    id: SnowflakeIdStr = Field(description="字段主键")
    form_code: str = Field(description="表单标识")
    field_key: str = Field(description="字段键")
    name: str = Field(description="字段名（当前 locale）")
    type: str = Field(description="字段类型")
    option_set_key: str | None = Field(default=None, description="选项集标识")
    column_name: str = Field(description="物理列名（ext_ 前缀）")
    table_name: str = Field(description="目标物理表名")
    ddl_status: str = Field(description="建列生命周期（pending / active / failed）")
    sort: int = Field(description="排序")
    status: str = Field(description="状态（enabled / disabled）")
    names: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="多语言名（locale → 文案）"
    )


class ExtFieldListResponse(BaseSchema):
    """自建字段清单响应。"""

    items: Annotated[ConcurrentStableList[ExtFieldItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="自建字段清单（sort 升序）"
    )
