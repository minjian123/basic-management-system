"""帮助读者面端点（`/api/v1/help/*`，12_01）。

- **鉴权**：仅 `require_auth`（登录即可）——与页面内帮助 `/help/context` 同口径；
- **语言**：路由级 `locale_scope` 解析请求语言与系统默认语言；
- **可见性**：草稿 / 下架文章在读者面返回 `40016`，不暴露存在性。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.core.context import get_current_user_id
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.api.locale import locale_scope
from bms_platform.domains.help.api.deps import ReaderServiceDep
from bms_platform.domains.help.schemas.feedback import HelpFeedbackRequest, HelpFeedbackResult
from bms_platform.domains.help.schemas.reader import (
    HelpReaderArticleDetail,
    HelpReaderArticlePage,
    HelpReaderCategoryTree,
)

__all__ = ["router"]

router = BaseRouter(
    key="help_reader",
    prefix="/help",
    tags=["help"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

PageDep = Annotated[BasePageQuery, Depends(page_query)]


@router.get("/categories")
async def list_categories(service: ReaderServiceDep) -> ApiResponse[HelpReaderCategoryTree]:
    """读者面分类树（启用分类 + 已发布文章数含子孙）。

    Args:
        service: 读者面服务。

    Returns:
        ApiResponse[HelpReaderCategoryTree]: 统一响应，data 为分类树。
    """
    return ApiResponse.ok(await service.list_categories())


@router.get("/articles")
async def list_articles(
    service: ReaderServiceDep,
    page: PageDep,
    category_id: Annotated[int | None, Query(description="分类 ID（含子孙；不传为全部）")] = None,
) -> ApiResponse[HelpReaderArticlePage]:
    """读者面文章列表（仅已发布；置顶优先）。

    Args:
        service: 读者面服务。
        page: 统一分页参数。
        category_id: 分类 ID（含子孙）。

    Returns:
        ApiResponse[HelpReaderArticlePage]: 统一响应，data 为分页文章。
    """
    return ApiResponse.ok(await service.list_articles(category_id=category_id, page=page.page, size=page.size))


@router.get("/articles/{article_id}")
async def get_article(article_id: int, service: ReaderServiceDep) -> ApiResponse[HelpReaderArticleDetail]:
    """读者面文章详情（阅读计数 +1 + 我的反馈）。

    文章不存在 / 草稿 / 下架返回 `40016`（不暴露存在性）。

    Args:
        article_id: 文章 ID。
        service: 读者面服务。

    Returns:
        ApiResponse[HelpReaderArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.get_article(article_id, user_id=get_current_user_id() or 0))


@router.post("/articles/{article_id}/feedback")
async def submit_feedback(
    article_id: int,
    payload: HelpFeedbackRequest,
    service: ReaderServiceDep,
) -> ApiResponse[HelpFeedbackResult]:
    """提交 / 改投反馈（同用户同文章唯一）。

    反馈类型非法 / 评论超长返回 `40020`；文章不可见返回 `40016`。

    Args:
        article_id: 文章 ID。
        payload: 反馈请求。
        service: 读者面服务。

    Returns:
        ApiResponse[HelpFeedbackResult]: 统一响应，data 为反馈结果。
    """
    return ApiResponse.ok(
        await service.submit_feedback(article_id, user_id=get_current_user_id() or 0, payload=payload)
    )
