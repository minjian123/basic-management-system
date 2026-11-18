"""帮助读者面请求 / 响应模型（`/help/*`，12_01）。

读者面只返回当前语言与已发布内容；PC 与移动端复用同一契约，移动端只改布局。
"""

from __future__ import annotations

from datetime import datetime
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
    "HelpReaderArticleDetail",
    "HelpReaderArticleItem",
    "HelpReaderArticlePage",
    "HelpReaderCategoryNode",
    "HelpReaderCategoryTree",
]


class HelpReaderCategoryNode(BaseSchema):
    """读者面分类节点（启用分类 + 已发布文章数）。"""

    id: SnowflakeIdStr = Field(description="分类主键")
    name: str = Field(description="分类名（当前语言）")
    sort: int = Field(description="同级排序（升序）")
    published_count: int = Field(ge=0, description="直接归属的已发布文章数")
    subtree_published_count: int = Field(ge=0, description="含子孙的已发布文章数")
    children: Annotated[ConcurrentStableList[HelpReaderCategoryNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="子分类"
    )


class HelpReaderCategoryTree(BaseSchema):
    """读者面分类树响应。"""

    items: Annotated[ConcurrentStableList[HelpReaderCategoryNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="根级分类（空分类保留）"
    )
    total: int = Field(ge=0, description="分类总数（含子孙）")


class HelpReaderArticleItem(BaseSchema):
    """读者面文章列表行（不含正文）。"""

    id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题（当前语言）")
    summary: str = Field(description="正文摘要（去标签截断）")
    category_id: SnowflakeIdStr = Field(description="分类主键")
    category_path: str = Field(description="分类路径（根 → 叶）")
    is_top: bool = Field(description="是否置顶")
    publish_at: datetime | None = Field(default=None, description="发布时间（UTC）")
    view_count: int = Field(ge=0, description="阅读数")
    helpful_count: int = Field(ge=0, description="有帮助数")
    unhelpful_count: int = Field(ge=0, description="无帮助数")


class HelpReaderArticlePage(BaseSchema):
    """读者面文章分页响应。"""

    list: Annotated[ConcurrentStableList[HelpReaderArticleItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="文章行（置顶优先）"
    )
    total: int = Field(ge=0, description="总数")
    page: int = Field(ge=1, description="页码")
    size: int = Field(ge=1, description="每页条数")


class HelpReaderArticleDetail(BaseSchema):
    """读者面文章详情（当前语言 + 我的反馈）。"""

    id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题（当前语言）")
    content: str = Field(description="正文 HTML（已清洗）")
    category_id: SnowflakeIdStr = Field(description="分类主键")
    category_path: str = Field(description="分类路径（根 → 叶）")
    publish_at: datetime | None = Field(default=None, description="发布时间（UTC）")
    view_count: int = Field(ge=0, description="阅读数")
    helpful_count: int = Field(ge=0, description="有帮助数")
    unhelpful_count: int = Field(ge=0, description="无帮助数")
    my_feedback: str | None = Field(default=None, description="当前用户的反馈（helpful / unhelpful；未投为空）")


HelpReaderCategoryNode.model_rebuild()
