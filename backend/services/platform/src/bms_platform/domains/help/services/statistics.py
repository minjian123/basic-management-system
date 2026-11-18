"""帮助统计视图服务（12_01）：按文章 / 分类聚合阅读与反馈。

口径（详细设计 §6.4）：

- 帮助率 = helpful / (helpful + unhelpful)，分母为 0 返回 `null`（不是 0，前端显示「—」）；
- 反馈率 = 反馈数 / 阅读数，阅读为 0 返回 `null`；
- 汇总头恒为全量口径（不受明细分页与筛选影响），明细受 `category_id` / `keyword` 影响；
- 明细固定序（阅读量倒序），不开放用户排序，避免为计算列造索引。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.help.values import (
    ARTICLE_STATUS_DRAFT,
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
)
from bms_core.models.platform.help import SysHelpCategory
from bms_platform.domains.help.constants import MAX_STAT_PAGE_SIZE
from bms_platform.domains.help.repositories.maintenance import (
    ArticleStatRow,
    CategoryStatRow,
    HelpArticleFilters,
    HelpArticleMaintenanceRepository,
)
from bms_platform.domains.help.schemas.statistics import (
    HelpStatisticArticleItem,
    HelpStatisticCategoryItem,
    HelpStatistics,
    HelpStatisticSummary,
)

__all__ = ["GROUP_BY_ARTICLE", "GROUP_BY_CATEGORY", "HelpStatisticsService"]

GROUP_BY_ARTICLE = "article"
"""分组维度：文章。"""

GROUP_BY_CATEGORY = "category"
"""分组维度：分类。"""

_GROUP_BY_VALUES: ConcurrentStableList[str] = ConcurrentStableList((GROUP_BY_ARTICLE, GROUP_BY_CATEGORY))
"""允许的分组维度。"""


class HelpStatisticsService(BaseFrameworkObject):
    """帮助统计视图服务。"""

    def __init__(self, *, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._repo = HelpArticleMaintenanceRepository(session)

    async def load(
        self,
        *,
        group_by: str,
        category_id: int | None,
        keyword: str | None,
        page: int,
        size: int,
    ) -> HelpStatistics:
        """取统计视图。

        Args:
            group_by: 分组维度（article / category）。
            category_id: 分类过滤（仅文章维度生效）。
            keyword: 标题关键字（仅文章维度生效）。
            page: 页码。
            size: 每页条数。

        Returns:
            HelpStatistics: 统计视图。

        Raises:
            ParamError: 分组维度非法或分页超限（`10001`）。
        """
        if group_by not in _GROUP_BY_VALUES:
            raise ParamError(f"分组维度非法：{group_by}")
        if size > MAX_STAT_PAGE_SIZE:
            raise ParamError(f"每页条数超出上限（{MAX_STAT_PAGE_SIZE}）")
        summary = await self._summary()
        categories = await self._repo.list_categories()
        paths = self._repo.content.build_path_map(categories)
        if group_by == GROUP_BY_CATEGORY:
            rows = await self._repo.category_stats()
            items = self._category_items(rows, categories, paths)
            start = (page - 1) * size
            page_items = ConcurrentStableList(items[start : start + size])
            return HelpStatistics(
                group_by=group_by,
                summary=summary,
                articles=ConcurrentStableList(),
                categories=page_items,
                total=len(items),
                page=page,
                size=size,
            )
        filters = HelpArticleFilters(category_id=category_id, keyword=keyword)
        rows, total = await self._repo.article_stats(filters, offset=(page - 1) * size, limit=size)
        return HelpStatistics(
            group_by=group_by,
            summary=summary,
            articles=ConcurrentStableList(self._article_item(row, paths) for row in rows),
            categories=ConcurrentStableList(),
            total=total,
            page=page,
            size=size,
        )

    async def _summary(self) -> HelpStatisticSummary:
        """取全量汇总头。

        Returns:
            HelpStatisticSummary: 汇总头。
        """
        rows = await self._repo.status_summary()
        by_status: ConcurrentStableDict[str, int] = ConcurrentStableDict(
            (row.status, row.article_count) for row in rows
        )
        article_count = sum(row.article_count for row in rows)
        total_views = sum(row.view_count for row in rows)
        helpful = sum(row.helpful_count for row in rows)
        unhelpful = sum(row.unhelpful_count for row in rows)
        feedback = helpful + unhelpful
        return HelpStatisticSummary(
            article_count=article_count,
            published_count=by_status.get(ARTICLE_STATUS_PUBLISHED, 0),
            draft_count=by_status.get(ARTICLE_STATUS_DRAFT, 0),
            offline_count=by_status.get(ARTICLE_STATUS_OFFLINE, 0),
            total_views=total_views,
            feedback_count=feedback,
            helpful_count=helpful,
            unhelpful_count=unhelpful,
            helpful_rate=_rate(helpful, helpful + unhelpful),
            feedback_rate=_rate(feedback, total_views),
        )

    def _article_item(self, row: ArticleStatRow, paths: ConcurrentStableDict[int, str]) -> HelpStatisticArticleItem:
        """文章统计行 → 契约行。

        Args:
            row: 聚合行。
            paths: 分类路径映射。

        Returns:
            HelpStatisticArticleItem: 契约行。
        """
        feedback = row.helpful_count + row.unhelpful_count
        return HelpStatisticArticleItem(
            article_id=row.article_id,
            title=row.title,
            category_id=row.category_id,
            category_path=paths.get(row.category_id, ""),
            status=row.status,
            view_count=row.view_count,
            feedback_count=feedback,
            helpful_count=row.helpful_count,
            unhelpful_count=row.unhelpful_count,
            helpful_rate=_rate(row.helpful_count, feedback),
            feedback_rate=_rate(feedback, row.view_count),
        )

    def _category_items(
        self,
        rows: ConcurrentStableList[CategoryStatRow],
        categories: ConcurrentStableList[SysHelpCategory],
        paths: ConcurrentStableDict[int, str],
    ) -> ConcurrentStableList[HelpStatisticCategoryItem]:
        """分类统计行 → 契约行（按阅读量倒序、主键升序）。

        Args:
            rows: 聚合行。
            categories: 分类行（取名称）。
            paths: 分类路径映射。

        Returns:
            ConcurrentStableList[HelpStatisticCategoryItem]: 契约行。
        """
        names: ConcurrentStableDict[int, str] = ConcurrentStableDict(
            (int(item.id), str(item.name)) for item in categories
        )
        items: ConcurrentStableList[HelpStatisticCategoryItem] = ConcurrentStableList()
        for row in rows:
            feedback = row.helpful_count + row.unhelpful_count
            items.add(
                HelpStatisticCategoryItem(
                    category_id=row.category_id,
                    name=names.get(row.category_id, ""),
                    path=paths.get(row.category_id, ""),
                    article_count=row.article_count,
                    published_count=row.published_count,
                    view_count=row.view_count,
                    feedback_count=feedback,
                    helpful_count=row.helpful_count,
                    unhelpful_count=row.unhelpful_count,
                    helpful_rate=_rate(row.helpful_count, feedback),
                    feedback_rate=_rate(feedback, row.view_count),
                )
            )
        return ConcurrentStableList(items.sorted(key=lambda item: (-item.view_count, int(item.category_id))))


def _rate(numerator: int, denominator: int) -> float | None:
    """计算比率（分母为 0 返回 None）。

    Args:
        numerator: 分子。
        denominator: 分母。

    Returns:
        float | None: 比率（保留 4 位）；分母为 0 为 None。
    """
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)
