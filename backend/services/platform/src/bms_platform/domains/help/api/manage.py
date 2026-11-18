"""帮助内容管理面端点（`/api/v1/help/manage/*`，12_01）。

- **鉴权**：`require_auth` + `help:manage`（维护与统计同一权限码）；
- **写路径**：由 06_01 操作审计中间件自动记录；文章字段级审计由 06_02 ORM 捕获自动入链；
- **路径分词**：读者面 `/help/*`、管理面 `/help/manage/*`、帮助包 `/help/packages/*`，响应形状不随权限变化。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query, Request

from bms_core.api.base import BaseRouter, page_query, require_auth
from bms_core.permission.base import require_permission
from bms_core.schemas.common import ApiResponse
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.api.locale import accept_locale, locale_scope
from bms_platform.domains.help.api.deps import MaintenanceServiceDep, StatisticsServiceDep
from bms_platform.domains.help.repositories.maintenance import HelpArticleFilters
from bms_platform.domains.help.schemas.article import (
    HelpManageArticleCreate,
    HelpManageArticleDeleteResult,
    HelpManageArticleDetail,
    HelpManageArticlePage,
    HelpManageArticleUpdate,
)
from bms_platform.domains.help.schemas.category import (
    HelpManageCategoryCreate,
    HelpManageCategoryDeleteResult,
    HelpManageCategoryNode,
    HelpManageCategoryTree,
    HelpManageCategoryUpdate,
)
from bms_platform.domains.help.schemas.statistics import HelpStatistics

__all__ = ["router"]

router = BaseRouter(
    key="help_manage",
    prefix="/help/manage",
    tags=["help"],
    dependencies=[Depends(require_auth), Depends(locale_scope)],
)

_REQUIRE_MANAGE = Depends(require_permission("help:manage"))
"""维护与统计统一权限码（概要 17 §6）。"""

PageDep = Annotated[BasePageQuery, Depends(page_query)]

_STATUS_QUERY = Annotated[str | None, Query(pattern="^(draft|published|offline)$", description="文章状态")]
_SOURCE_QUERY = Annotated[str | None, Query(pattern="^(builtin|product|tenant)$", description="文章来源")]


# --------------------------------------------------------------------- 分类


@router.get("/categories", dependencies=[_REQUIRE_MANAGE])
async def list_categories(service: MaintenanceServiceDep) -> ApiResponse[HelpManageCategoryTree]:
    """管理面分类树（含停用与各状态计数）。

    Args:
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageCategoryTree]: 统一响应，data 为分类树。
    """
    return ApiResponse.ok(await service.list_categories())


@router.post("/categories", dependencies=[_REQUIRE_MANAGE])
async def create_category(
    payload: HelpManageCategoryCreate,
    service: MaintenanceServiceDep,
) -> ApiResponse[HelpManageCategoryNode]:
    """新建分类。

    父级不存在 `40014`；同级同名 / 深度超限 `40023`；状态非法 `10001`。

    Args:
        payload: 新建请求。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageCategoryNode]: 统一响应，data 为新建节点。
    """
    return ApiResponse.ok(await service.create_category(payload))


@router.put("/categories/{category_id}", dependencies=[_REQUIRE_MANAGE])
async def update_category(
    category_id: int,
    payload: HelpManageCategoryUpdate,
    service: MaintenanceServiceDep,
) -> ApiResponse[HelpManageCategoryNode]:
    """编辑分类（名称 / 父级 / 排序 / 状态）。

    分类或父级不存在 `40014`；同级同名 / 成环 / 深度超限 `40023`。

    Args:
        category_id: 分类 ID。
        payload: 编辑请求。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageCategoryNode]: 统一响应，data 为更新后的节点。
    """
    return ApiResponse.ok(await service.update_category(category_id, payload))


@router.delete("/categories/{category_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_category(
    category_id: int,
    service: MaintenanceServiceDep,
    cascade: Annotated[bool, Query(description="是否级联下架子树文章后删除")] = False,
) -> ApiResponse[HelpManageCategoryDeleteResult]:
    """删除分类（默认拒删；级联下架子树文章）。

    存在子分类或文章且未级联 `40015`；分类不存在 `40014`。

    Args:
        category_id: 分类 ID。
        service: 维护服务。
        cascade: 是否级联。

    Returns:
        ApiResponse[HelpManageCategoryDeleteResult]: 统一响应，data 为删除计数。
    """
    return ApiResponse.ok(await service.delete_category(category_id, cascade=cascade))


# --------------------------------------------------------------------- 文章


@router.get("/articles", dependencies=[_REQUIRE_MANAGE])
async def list_articles(
    service: MaintenanceServiceDep,
    page: PageDep,
    category_id: Annotated[int | None, Query(description="分类 ID（精确匹配）")] = None,
    status: _STATUS_QUERY = None,
    source: _SOURCE_QUERY = None,
    keyword: Annotated[str | None, Query(max_length=128, description="标题关键字")] = None,
) -> ApiResponse[HelpManageArticlePage]:
    """管理面文章列表（全状态）。

    Args:
        service: 维护服务。
        page: 统一分页参数。
        category_id: 分类 ID。
        status: 文章状态。
        source: 文章来源。
        keyword: 标题关键字。

    Returns:
        ApiResponse[HelpManageArticlePage]: 统一响应，data 为分页文章。
    """
    filters = HelpArticleFilters(
        category_id=category_id,
        status=status,
        source=source,
        keyword=keyword,
    )
    return ApiResponse.ok(await service.list_articles(filters, page=page.page, size=page.size))


@router.get("/articles/{article_id}", dependencies=[_REQUIRE_MANAGE])
async def get_article(article_id: int, service: MaintenanceServiceDep) -> ApiResponse[HelpManageArticleDetail]:
    """管理面文章详情（全语言 + 目标 + 计数 + 来源留痕）。

    Args:
        article_id: 文章 ID。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.get_article(article_id))


@router.post("/articles", dependencies=[_REQUIRE_MANAGE])
async def create_article(
    request: Request,
    payload: HelpManageArticleCreate,
    service: MaintenanceServiceDep,
) -> ApiResponse[HelpManageArticleDetail]:
    """新建文章（默认草稿）。

    内容非法 / AI 未审核 `40018`；语言不受支持 `40022`；锚点不可解析 `40008`；目标冲突 `40019`。

    Args:
        request: 请求对象（取请求语言）。
        payload: 新建请求。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.create_article(payload, locale=accept_locale(request)))


@router.put("/articles/{article_id}", dependencies=[_REQUIRE_MANAGE])
async def update_article(
    request: Request,
    article_id: int,
    payload: HelpManageArticleUpdate,
    service: MaintenanceServiceDep,
) -> ApiResponse[HelpManageArticleDetail]:
    """编辑文章（显式状态，缺省沿用；包来源自动本地覆盖）。

    状态迁移不允许 `40017`；内容非法 / AI 未审核 `40018`；锚点不可解析 `40008`；目标冲突 `40019`。

    Args:
        request: 请求对象（取请求语言）。
        article_id: 文章 ID。
        payload: 编辑请求。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.update_article(article_id, payload, locale=accept_locale(request)))


@router.delete("/articles/{article_id}", dependencies=[_REQUIRE_MANAGE])
async def delete_article(article_id: int, service: MaintenanceServiceDep) -> ApiResponse[HelpManageArticleDeleteResult]:
    """软删除文章（产品包来源文章拒绝，引导下架）。

    文章不存在 `40016`；包来源文章 `40017`。

    Args:
        article_id: 文章 ID。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDeleteResult]: 统一响应，data 为删除结果。
    """
    return ApiResponse.ok(await service.delete_article(article_id))


@router.post("/articles/{article_id}/publish", dependencies=[_REQUIRE_MANAGE])
async def publish_article(article_id: int, service: MaintenanceServiceDep) -> ApiResponse[HelpManageArticleDetail]:
    """发布文章（草稿 / 下架 → 已发布）。

    状态迁移不允许 `40017`；AI 未审核 `40018`。

    Args:
        article_id: 文章 ID。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.publish_article(article_id))


@router.post("/articles/{article_id}/offline", dependencies=[_REQUIRE_MANAGE])
async def offline_article(article_id: int, service: MaintenanceServiceDep) -> ApiResponse[HelpManageArticleDetail]:
    """下架文章（已发布 → 已下架）。

    状态迁移不允许 `40017`。

    Args:
        article_id: 文章 ID。
        service: 维护服务。

    Returns:
        ApiResponse[HelpManageArticleDetail]: 统一响应，data 为文章详情。
    """
    return ApiResponse.ok(await service.offline_article(article_id))


# --------------------------------------------------------------------- 统计


@router.get("/statistics", dependencies=[_REQUIRE_MANAGE])
async def statistics(
    service: StatisticsServiceDep,
    page: PageDep,
    group_by: Annotated[str, Query(pattern="^(article|category)$", description="分组维度")] = "article",
    category_id: Annotated[int | None, Query(description="分类过滤（仅文章维度）")] = None,
    keyword: Annotated[str | None, Query(max_length=128, description="标题关键字（仅文章维度）")] = None,
) -> ApiResponse[HelpStatistics]:
    """阅读与反馈统计视图（按文章 / 分类分组）。

    Args:
        service: 统计服务。
        page: 统一分页参数。
        group_by: 分组维度（article / category）。
        category_id: 分类过滤（仅文章维度）。
        keyword: 标题关键字（仅文章维度）。

    Returns:
        ApiResponse[HelpStatistics]: 统一响应，data 为统计视图。
    """
    return ApiResponse.ok(
        await service.load(
            group_by=group_by,
            category_id=category_id,
            keyword=keyword,
            page=page.page,
            size=page.size,
        )
    )
