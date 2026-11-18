"""工作台卡片请求 / 响应模型（`/dashboard/cards`）。

集合字段一律插入序集合类 + `CONTRACT_COLLECTION` 注解（不用裸 `list` / `dict`）；
主键按 `SnowflakeIdStr` 字符串化（JS 安全整数）。
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
    "DashboardCardCreate",
    "DashboardCardDeleteResult",
    "DashboardCardList",
    "DashboardCardMeta",
    "DashboardCardRow",
    "DashboardCardUpdate",
]


class DashboardCardMeta(BaseSchema):
    """卡片元数据（布局接口 `available_cards` 项，前端渲染依据）。"""

    code: str = Field(min_length=2, max_length=64, description="卡片标识")
    name: str = Field(min_length=1, max_length=128, description="卡片名（当前语言）")
    card_type: str = Field(min_length=1, max_length=16, description="卡片类型（builtin / dataset）")
    render_key: str = Field(default="", max_length=64, description="前端渲染器标识（内置卡必填）")
    dataset_id: str | None = Field(default=None, max_length=64, description="数据集标识（仅数据集卡）")
    chart_type: str | None = Field(default=None, max_length=32, description="图表类型（仅数据集卡）")
    chart_config: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None,
        description="图表样式覆盖（可选；非法配置由前端忽略并回退默认）",
    )
    default_width: int = Field(ge=2, le=12, description="默认宽（列）")
    default_height: int = Field(ge=2, le=6, description="默认高（行）")
    mobile_supported: bool = Field(description="是否参与移动端单列布局")
    data_endpoint: str = Field(default="", max_length=256, description="卡片数据接口地址（空表示前端自取或占位）")
    sort: int = Field(description="排序（升序）")


class DashboardCardRow(DashboardCardMeta):
    """卡片管理面行（多状态与多语言文案）。"""

    id: SnowflakeIdStr = Field(description="卡片主键")
    status: str = Field(min_length=1, max_length=16, description="状态（enabled / disabled）")
    i18n: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT,
        description="语言 → 卡片名（含默认语言）",
    )


class DashboardCardList(BaseSchema):
    """卡片列表响应。"""

    items: Annotated[ConcurrentStableList[DashboardCardRow], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="卡片清单（按 sort 升序）"
    )
    total: int = Field(ge=0, description="总数")


class DashboardCardCreate(BaseSchema):
    """新建卡片请求（只允许数据集卡）。"""

    code: str = Field(min_length=2, max_length=64, description="卡片标识（小写字母开头，仅小写字母 / 数字 / 下划线）")
    name: str = Field(min_length=1, max_length=128, description="卡片名（默认语言文案）")
    card_type: str = Field(default="dataset", max_length=16, description="卡片类型（只允许 dataset）")
    dataset_id: str = Field(min_length=1, max_length=64, description="数据集标识（逻辑外键 → 报表中心数据集）")
    chart_type: str = Field(min_length=1, max_length=32, description="图表类型（取图表类型白名单）")
    chart_config: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="图表样式覆盖（可选）"
    )
    default_width: int = Field(default=4, ge=2, le=12, description="默认宽（列）")
    default_height: int = Field(default=2, ge=2, le=6, description="默认高（行）")
    mobile_supported: bool = Field(default=True, description="是否参与移动端单列布局")
    sort: int = Field(default=0, description="排序（升序）")
    status: str = Field(default="enabled", max_length=16, description="状态（enabled / disabled）")
    i18n: Annotated[ConcurrentStableDict[str, str], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="语言 → 卡片名（可选；缺省语言按派生规则兜底）"
    )


class DashboardCardUpdate(BaseSchema):
    """编辑卡片请求（数据集卡全字段；内置卡只允许 `status`）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="卡片名")
    dataset_id: str | None = Field(default=None, min_length=1, max_length=64, description="数据集标识")
    chart_type: str | None = Field(default=None, min_length=1, max_length=32, description="图表类型")
    chart_config: Annotated[ConcurrentStableDict[str, object] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="图表样式覆盖（None 表示不修改）"
    )
    default_width: int | None = Field(default=None, ge=2, le=12, description="默认宽（列）")
    default_height: int | None = Field(default=None, ge=2, le=6, description="默认高（行）")
    mobile_supported: bool | None = Field(default=None, description="是否参与移动端单列布局")
    sort: int | None = Field(default=None, description="排序（升序）")
    status: str | None = Field(default=None, max_length=16, description="状态（enabled / disabled）")
    i18n: Annotated[ConcurrentStableDict[str, str] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="语言 → 卡片名（None 表示不修改；整份覆盖）"
    )


class DashboardCardDeleteResult(BaseSchema):
    """删除卡片结果。"""

    applied: bool = Field(description="是否删除到既有卡片")
