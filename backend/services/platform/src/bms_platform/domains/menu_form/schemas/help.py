"""帮助解析契约：页面内帮助的五级解析响应（`GET /api/v1/help/context`）。

命中返回文章与锚点定位；未命中返回空 + 分类列表（前端据此提示「暂无帮助」并打开分类）。
`button_visible` 恒等于 `matched`：锚点已登记且有可展示文章才显示帮助按钮。
"""

from typing import Annotated

from pydantic import Field

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.schemas.base import CONTRACT_COLLECTION, CONTRACT_STABLE_LIST, BaseSchema, SnowflakeIdStr

__all__ = ["HelpArticleItem", "HelpArticleSummaryItem", "HelpCategoryItem", "HelpContextResponse"]


class HelpArticleItem(BaseSchema):
    """命中文章（含正文；页面内帮助一次请求即可弹窗）。"""

    id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题（按请求语言解析）")
    content: str = Field(description="正文（已清洗 HTML）")
    source: str = Field(description="来源（builtin 平台内建 / product 产品包 / tenant 租户维护）")


class HelpArticleSummaryItem(BaseSchema):
    """文章摘要（「相关内容」列表用，不含正文）。"""

    id: SnowflakeIdStr = Field(description="文章主键")
    title: str = Field(description="标题")
    source: str = Field(description="来源（builtin / product / tenant）")


class HelpCategoryItem(BaseSchema):
    """帮助分类摘要（未命中兜底列表用）。"""

    id: SnowflakeIdStr = Field(description="分类主键")
    name: str = Field(description="分类名（按请求语言解析）")
    path: str = Field(description="分类路径（/ 分隔，自根到本节点）")


class HelpContextResponse(BaseSchema):
    """页面内帮助解析结果。"""

    matched: bool = Field(description="是否命中可展示文章（按钮显隐判据）")
    level: str | None = Field(
        default=None,
        description="命中层级（field 字段 / action 动作 / form 表单 / module 模块 / global 全局；未命中为 null）",
    )
    help_key: str | None = Field(default=None, description="命中锚点（全局级与未命中为 null）")
    article: HelpArticleItem | None = Field(default=None, description="命中文章（未命中为 null）")
    related: Annotated[ConcurrentStableList[HelpArticleSummaryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="同一锚点的其余文章（相关内容）"
    )
    categories: Annotated[ConcurrentStableList[HelpCategoryItem], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_LIST, description="分类列表（未命中时前端据此打开分类）"
    )
    button_visible: bool = Field(description="帮助按钮显隐（锚点已登记且有可展示文章才为 true）")
