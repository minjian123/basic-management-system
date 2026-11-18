"""帮助分类管理面请求 / 响应模型（`/help/manage/categories`，12_01）。

- 树节点递归引用自身（`children`），契约生成时按 `$ref` 展开；
- 计数列区分「直接归属」与「含子孙」两种口径，前端按需展示；
- 主键按 `SnowflakeIdStr` 字符串化（JS 安全整数）。
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
    "HelpManageCategoryCreate",
    "HelpManageCategoryDeleteResult",
    "HelpManageCategoryNode",
    "HelpManageCategoryTree",
    "HelpManageCategoryUpdate",
]


class HelpManageCategoryNode(BaseSchema):
    """管理面分类节点（含停用与各状态计数）。"""

    id: SnowflakeIdStr = Field(description="分类主键")
    parent_id: SnowflakeIdStr = Field(description="上级分类 ID（0 = 根）")
    name: str = Field(min_length=1, max_length=128, description="分类名")
    sort: int = Field(description="同级排序（升序）")
    status: str = Field(min_length=1, max_length=16, description="状态（enabled / disabled）")
    article_count: int = Field(ge=0, description="直接归属的未删文章数")
    subtree_article_count: int = Field(ge=0, description="含子孙的未删文章数")
    published_count: int = Field(ge=0, description="直接归属的已发布文章数")
    draft_count: int = Field(ge=0, description="直接归属的草稿数")
    offline_count: int = Field(ge=0, description="直接归属的已下架数")
    children: Annotated[ConcurrentStableList[HelpManageCategoryNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="子分类（同级按 sort 升序）"
    )


class HelpManageCategoryTree(BaseSchema):
    """管理面分类树响应。"""

    items: Annotated[ConcurrentStableList[HelpManageCategoryNode], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="根级分类"
    )
    total: int = Field(ge=0, description="分类总数（含子孙）")


class HelpManageCategoryCreate(BaseSchema):
    """新建分类请求。"""

    name: str = Field(min_length=1, max_length=128, description="分类名（同父级唯一）")
    parent_id: SnowflakeIdStr = Field(default=0, description="上级分类 ID（0 = 根）")
    sort: int = Field(default=0, description="同级排序（升序）")
    status: str = Field(default="enabled", max_length=16, description="状态（enabled / disabled）")


class HelpManageCategoryUpdate(BaseSchema):
    """编辑分类请求（字段可选；`parent_id` 变更须保证不成环且不超深度）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128, description="分类名")
    parent_id: SnowflakeIdStr | None = Field(default=None, description="上级分类 ID（0 = 根）")
    sort: int | None = Field(default=None, description="同级排序（升序）")
    status: str | None = Field(default=None, max_length=16, description="状态（enabled / disabled）")


class HelpManageCategoryDeleteResult(BaseSchema):
    """删除分类结果（默认拒删时由错误响应给出计数）。"""

    deleted_categories: int = Field(ge=0, description="软删除的分类数（含子树）")
    offlined_articles: int = Field(ge=0, description="级联下架的文章数")


HelpManageCategoryNode.model_rebuild()
