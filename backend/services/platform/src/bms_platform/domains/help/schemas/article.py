"""帮助文章管理面请求 / 响应模型（`/help/manage/articles`，12_01）。

- 请求体 `title` / `content` 是**默认语言**文案（便捷入口）；`i18n` 给全语言映射，缺默认语言时用前者补齐；
- `targets` 传 `null`（缺省）表示不修改，传空数组表示清空；`global` 目标的 `key` 必须为空；
- 响应按管理面口径返回全部语言与目标，读者面只返回当前语言（见 `schemas/reader.py`）。
"""

from __future__ import annotations

from datetime import datetime
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
    "HelpManageArticleCreate",
    "HelpManageArticleDeleteResult",
    "HelpManageArticleDetail",
    "HelpManageArticleItem",
    "HelpManageArticlePage",
    "HelpManageArticleUpdate",
    "HelpManageLocaleText",
    "HelpManageTargetItem",
]


class HelpManageTargetItem(BaseSchema):
    """文章目标（锚点）项。"""

    type: str = Field(min_length=1, max_length=16, description="目标类型（global / module / form / field / action）")
    key: str = Field(default="", max_length=255, description="锚点键（global 为空串；其余为五段式 help_key）")


class HelpManageLocaleText(BaseSchema):
    """单语言标题与正文。"""

    title: str = Field(min_length=1, max_length=256, description="标题")
    content: str = Field(default="", max_length=120000, description="正文 HTML（服务端白名单清洗）")


class HelpManageArticleItem(BaseSchema):
    """管理面文章列表行。"""

    id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题（默认语言快照）")
    category_id: SnowflakeIdStr = Field(description="分类主键")
    category_path: str = Field(default="", description="分类路径（根 → 叶）")
    status: str = Field(min_length=1, max_length=16, description="状态（draft / published / offline）")
    is_top: bool = Field(description="是否置顶")
    source: str = Field(min_length=1, max_length=16, description="来源（builtin / product / tenant）")
    local_override: bool = Field(description="是否被租户本地编辑（升级不覆盖内容）")
    generated_by: str = Field(min_length=1, max_length=16, description="生成方式（manual / ai）")
    reviewed_by: str | None = Field(default=None, description="审核人（AI 草稿发布前置）")
    publish_at: datetime | None = Field(default=None, description="发布时间（UTC）")
    view_count: int = Field(ge=0, description="阅读数")
    helpful_count: int = Field(ge=0, description="有帮助数")
    unhelpful_count: int = Field(ge=0, description="无帮助数")
    updated_at: datetime | None = Field(default=None, description="最后修改时间（UTC）")


class HelpManageArticlePage(BaseSchema):
    """管理面文章分页响应。"""

    list: Annotated[ConcurrentStableList[HelpManageArticleItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="文章行"
    )
    total: int = Field(ge=0, description="总数")
    page: int = Field(ge=1, description="页码")
    size: int = Field(ge=1, description="每页条数")


class HelpManageArticleDetail(HelpManageArticleItem):
    """管理面文章详情（含正文、全部语言与目标）。"""

    content: str = Field(default="", description="正文 HTML（默认语言快照）")
    i18n: Annotated[ConcurrentStableDict[str, HelpManageLocaleText], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="语言 → 标题与正文"
    )
    targets: Annotated[ConcurrentStableList[HelpManageTargetItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="目标（锚点）清单"
    )
    package_id: SnowflakeIdStr | None = Field(default=None, description="来源包版本主键（租户自建为空）")
    source_key: str | None = Field(default=None, description="包内稳定键（租户自建为空）")
    ai_model: str | None = Field(default=None, description="AI 生成模型（generated_by=ai 时填写）")
    author_id: SnowflakeIdStr | None = Field(default=None, description="人工作者主键（包装载为空）")
    created_at: datetime | None = Field(default=None, description="创建时间（UTC）")
    version: int = Field(ge=1, description="乐观锁版本")


class HelpManageArticleCreate(BaseSchema):
    """新建文章请求（默认草稿）。"""

    category_id: SnowflakeIdStr = Field(description="分类主键")
    title: str = Field(min_length=1, max_length=256, description="默认语言标题")
    content: str = Field(default="", max_length=120000, description="默认语言正文 HTML")
    status: str = Field(default="draft", max_length=16, description="状态（draft / published / offline；缺省草稿）")
    is_top: bool = Field(default=False, description="是否置顶")
    targets: Annotated[ConcurrentStableList[HelpManageTargetItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="目标（锚点）清单"
    )
    i18n: Annotated[ConcurrentStableDict[str, HelpManageLocaleText], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT, description="语言 → 标题与正文（缺默认语言时用 title / content 补齐）"
    )
    generated_by: str = Field(default="manual", max_length=16, description="生成方式（manual / ai）")
    ai_model: str | None = Field(default=None, max_length=64, description="AI 模型（generated_by=ai 时填写）")
    reviewed_by: str | None = Field(default=None, max_length=128, description="审核人（AI 草稿发布前置）")


class HelpManageArticleUpdate(BaseSchema):
    """编辑文章请求（字段可选；`status` 缺省沿用当前状态）。"""

    category_id: SnowflakeIdStr | None = Field(default=None, description="分类主键")
    title: str | None = Field(default=None, min_length=1, max_length=256, description="默认语言标题")
    content: str | None = Field(default=None, max_length=120000, description="默认语言正文 HTML")
    status: str | None = Field(default=None, max_length=16, description="状态（缺省沿用；发布 / 下架仍校验迁移）")
    is_top: bool | None = Field(default=None, description="是否置顶")
    targets: Annotated[ConcurrentStableList[HelpManageTargetItem] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="目标清单（None 不修改；空数组清空）"
    )
    i18n: Annotated[ConcurrentStableDict[str, HelpManageLocaleText] | None, CONTRACT_COLLECTION] = Field(
        default=None, description="语言 → 标题与正文（None 不修改；整份覆盖）"
    )
    generated_by: str | None = Field(default=None, max_length=16, description="生成方式")
    ai_model: str | None = Field(default=None, max_length=64, description="AI 模型")
    reviewed_by: str | None = Field(default=None, max_length=128, description="审核人")


class HelpManageArticleDeleteResult(BaseSchema):
    """删除文章结果。"""

    applied: bool = Field(description="是否删除到既有文章")
