"""工作台布局请求 / 响应模型（`/dashboard/layout`）。"""

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
from bms_platform.domains.dashboard.schemas.card import DashboardCardMeta

__all__ = [
    "DashboardLayoutCard",
    "DashboardLayoutIssue",
    "DashboardLayoutPayload",
    "DashboardLayoutResetResult",
    "DashboardLayoutResolve",
    "DashboardLayoutSaveRequest",
    "DashboardLayoutSaveResult",
    "DashboardLayoutStructure",
]


class DashboardLayoutCard(BaseSchema):
    """布局中的一张卡片（网格位置与尺寸）。"""

    code: str = Field(min_length=2, max_length=64, description="卡片标识")
    x: int = Field(ge=0, le=11, description="列偏移（0 ~ 12-w）")
    y: int = Field(ge=0, description="行偏移")
    w: int = Field(ge=2, le=12, description="宽（列）")
    h: int = Field(ge=2, le=6, description="高（行）")
    visible: bool = Field(default=True, description="是否可见（不可见不占网格）")


class DashboardLayoutPayload(BaseSchema):
    """布局载荷（模板与个人布局同形）。"""

    cards: Annotated[ConcurrentStableList[DashboardLayoutCard], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="卡片放置清单（插入序）"
    )


class DashboardLayoutIssue(BaseSchema):
    """布局问题 / 告警项。"""

    code: str = Field(default="", description="涉及的卡片标识（结构级问题为空串）")
    reason: str = Field(min_length=1, description="原因（card_disabled / card_unknown / overlap 等）")


class DashboardLayoutStructure(BaseSchema):
    """布局解析结构（缓存形态；不含可选卡片清单与文案）。"""

    layout: DashboardLayoutPayload = Field(description="生效布局")
    source: str = Field(min_length=1, description="来源层级（personal / role / platform / empty）")
    role_id: SnowflakeIdStr = Field(description="命中的角色模板角色主键（无则 0）")
    template_id: SnowflakeIdStr = Field(description="命中的模板主键（个人 / 内置回退为 0）")
    fallback: bool = Field(description="是否走到内置最小布局")
    warnings: Annotated[ConcurrentStableList[DashboardLayoutIssue], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="剔除告警（未注册 / 已停用卡片）"
    )


class DashboardLayoutResolve(DashboardLayoutStructure):
    """布局解析响应（结构 + 可选卡片清单）。"""

    available_cards: Annotated[ConcurrentStableList[DashboardCardMeta], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="可选卡片清单（全部启用卡，按 sort 升序）"
    )


class DashboardLayoutSaveRequest(BaseSchema):
    """保存个人布局请求（整份覆盖）。"""

    layout: Annotated[ConcurrentStableDict[str, object], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="布局配置（cards 清单）"
    )


class DashboardLayoutSaveResult(BaseSchema):
    """保存个人布局结果。"""

    applied: bool = Field(description="是否写入成功")
    warnings: Annotated[ConcurrentStableList[DashboardLayoutIssue], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="告警（引用已停用卡片等）"
    )


class DashboardLayoutResetResult(BaseSchema):
    """一键重置结果。"""

    applied: bool = Field(description="是否删除到既有个人布局")
