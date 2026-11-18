"""帮助统计视图响应模型（`/help/manage/statistics`，12_01）。

帮助率 = helpful / (helpful + unhelpful)，无反馈为 `null`（前端显示「—」）；
反馈率 = 反馈数 / 阅读数，阅读为 0 时为 `null`。
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_LIST,
    BaseSchema,
    SnowflakeIdStr,
)

__all__ = [
    "HelpStatisticArticleItem",
    "HelpStatisticCategoryItem",
    "HelpStatisticSummary",
    "HelpStatistics",
]


class HelpStatisticSummary(BaseSchema):
    """统计汇总头（全量口径，不受分页与明细筛选影响）。"""

    article_count: int = Field(ge=0, description="文章总数（未软删）")
    published_count: int = Field(ge=0, description="已发布数")
    draft_count: int = Field(ge=0, description="草稿数")
    offline_count: int = Field(ge=0, description="已下架数")
    total_views: int = Field(ge=0, description="阅读数合计")
    feedback_count: int = Field(ge=0, description="反馈数合计（有帮助 + 无帮助）")
    helpful_count: int = Field(ge=0, description="有帮助数合计")
    unhelpful_count: int = Field(ge=0, description="无帮助数合计")
    helpful_rate: float | None = Field(default=None, description="帮助率（无反馈为 null）")
    feedback_rate: float | None = Field(default=None, description="反馈率（无阅读为 null）")


class HelpStatisticArticleItem(BaseSchema):
    """按文章分组的明细行。"""

    article_id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题")
    category_id: SnowflakeIdStr = Field(description="分类主键")
    category_path: str = Field(default="", description="分类路径（根 → 叶）")
    status: str = Field(description="状态")
    view_count: int = Field(ge=0, description="阅读数")
    feedback_count: int = Field(ge=0, description="反馈数")
    helpful_count: int = Field(ge=0, description="有帮助数")
    unhelpful_count: int = Field(ge=0, description="无帮助数")
    helpful_rate: float | None = Field(default=None, description="帮助率（无反馈为 null）")
    feedback_rate: float | None = Field(default=None, description="反馈率（无阅读为 null）")


class HelpStatisticCategoryItem(BaseSchema):
    """按分类分组的明细行（直接归属）。"""

    category_id: SnowflakeIdStr = Field(description="分类主键")
    name: str = Field(description="分类名")
    path: str = Field(default="", description="分类路径（根 → 叶）")
    article_count: int = Field(ge=0, description="文章总数")
    published_count: int = Field(ge=0, description="已发布数")
    view_count: int = Field(ge=0, description="阅读数合计")
    feedback_count: int = Field(ge=0, description="反馈数合计")
    helpful_count: int = Field(ge=0, description="有帮助数合计")
    unhelpful_count: int = Field(ge=0, description="无帮助数合计")
    helpful_rate: float | None = Field(default=None, description="帮助率（无反馈为 null）")
    feedback_rate: float | None = Field(default=None, description="反馈率（无阅读为 null）")


class HelpStatistics(BaseSchema):
    """统计视图响应（`group_by` 决定哪个明细清单非空）。"""

    group_by: str = Field(description="分组维度（article / category）")
    summary: HelpStatisticSummary = Field(description="汇总头（全量口径）")
    articles: Annotated[ConcurrentStableList[HelpStatisticArticleItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="按文章分组的明细（group_by=category 时为空）"
    )
    categories: Annotated[ConcurrentStableList[HelpStatisticCategoryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="按分类分组的明细（group_by=article 时为空）"
    )
    total: int = Field(ge=0, description="明细总数")
    page: int = Field(ge=1, description="页码")
    size: int = Field(ge=1, description="每页条数")
