"""工作台模板请求 / 响应模型（`/dashboard/templates`）。"""

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
    "DashboardTemplateCreate",
    "DashboardTemplateDeleteResult",
    "DashboardTemplateList",
    "DashboardTemplateRow",
    "DashboardTemplateUpdate",
]


class DashboardTemplateRow(BaseSchema):
    """模板行（列表 / 详情）。"""

    id: SnowflakeIdStr = Field(description="模板主键")
    scope: str = Field(min_length=1, max_length=16, description="层级（platform / role）")
    role_id: SnowflakeIdStr = Field(description="角色 ID（平台层级固定 0）")
    name: str = Field(min_length=1, max_length=128, description="模板名称")
    status: str = Field(min_length=1, max_length=16, description="状态（enabled / disabled）")
    card_count: int = Field(ge=0, description="布局内卡片数")


class DashboardTemplateList(BaseSchema):
    """模板列表响应。"""

    items: Annotated[ConcurrentStableList[DashboardTemplateRow], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="模板清单（平台在前，角色按主键升序）"
    )
    total: int = Field(ge=0, description="总数")


class DashboardTemplateCreate(BaseSchema):
    """新建模板请求。"""

    scope: str = Field(min_length=1, max_length=16, description="层级（platform / role）")
    role_id: SnowflakeIdStr = Field(default=0, description="角色 ID（scope=role 必填；platform 固定 0）")
    name: str = Field(min_length=1, max_length=128, description="模板名称")
    layout_config: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="布局配置（cards 清单）"
    )
    status: str = Field(default="enabled", max_length=16, description="状态（enabled / disabled）")


class DashboardTemplateUpdate(BaseSchema):
    """编辑模板请求（`scope` 与 `role_id` 不可改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="模板名称")
    layout_config: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="布局配置（None 表示不修改）"
    )
    status: str | None = Field(default=None, max_length=16, description="状态（enabled / disabled）")


class DashboardTemplateDeleteResult(BaseSchema):
    """删除模板结果。"""

    applied: bool = Field(description="是否删除到既有模板")
