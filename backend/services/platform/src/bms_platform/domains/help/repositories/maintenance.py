"""帮助内容维护面数据访问：分类 / 文章 / 反馈 / 统计 / 包列表（12_01）。

只承载 SQL 与行操作，不含业务规则（状态机 / 锚点校验 / 事件 / 缓存失效在 `services/`）。
解析读面复用 `HelpContentRepository`（装载写的形状与解析读的形状同源）。

计数口径：

- 阅读 / 有帮助 / 无帮助计数一律单条 `UPDATE ... c = c + n`，不加载 ORM 行——
  避免高频计数把字段级审计链刷满（审计只覆盖内容变更）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select, update

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_PUBLISHED,
)
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
    SysHelpFeedback,
    SysHelpPackage,
)
from bms_platform.domains.help.repositories.content import HelpContentRepository

__all__ = [
    "ArticleStatRow",
    "CategoryStatRow",
    "HelpArticleFilters",
    "HelpArticleMaintenanceRepository",
    "StatusSummaryRow",
]

_CATEGORY_STATUS_ENABLED = "enabled"
"""分类启用状态（与表默认值一致）。"""


@dataclass(frozen=True)
class HelpArticleFilters(BaseValueObject):
    """管理面文章列表筛选（全部可选）。"""

    category_id: int | None = None
    """分类主键（精确匹配）。"""
    status: str | None = None
    """文章状态。"""
    source: str | None = None
    """文章来源。"""
    keyword: str | None = None
    """标题关键字（大小写不敏感，通配符转义）。"""


@dataclass(frozen=True)
class ArticleStatRow(BaseValueObject):
    """统计视图的文章行（聚合后的原始计数）。"""

    article_id: int
    """文章主键。"""
    title: str
    """标题。"""
    category_id: int
    """分类主键。"""
    status: str
    """状态。"""
    view_count: int
    """阅读数。"""
    helpful_count: int
    """有帮助数。"""
    unhelpful_count: int
    """无帮助数。"""


@dataclass(frozen=True)
class CategoryStatRow(BaseValueObject):
    """统计视图的分类行（聚合后的原始计数）。"""

    category_id: int
    """分类主键。"""
    article_count: int
    """文章总数（未软删）。"""
    published_count: int
    """已发布数。"""
    view_count: int
    """阅读数合计。"""
    helpful_count: int
    """有帮助数合计。"""
    unhelpful_count: int
    """无帮助数合计。"""


@dataclass(frozen=True)
class StatusSummaryRow(BaseValueObject):
    """统计汇总的按状态分桶（原始计数）。"""

    status: str
    """状态。"""
    article_count: int
    """该状态文章数。"""
    view_count: int
    """阅读数合计。"""
    helpful_count: int
    """有帮助数合计。"""
    unhelpful_count: int
    """无帮助数合计。"""


class HelpArticleMaintenanceRepository:
    """帮助内容维护仓储（租户库会话）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._session = session
        self.content = HelpContentRepository(session)

    # ---- 分类 ----

    async def list_categories(self) -> ConcurrentStableList[SysHelpCategory]:
        """取全部未软删分类（父级 → 排序 → 主键）。

        Returns:
            ConcurrentStableList[SysHelpCategory]: 分类行。
        """
        return await self.content.load_categories()

    async def get_category(self, category_id: int) -> SysHelpCategory | None:
        """按主键取未软删分类。

        Args:
            category_id: 分类主键。

        Returns:
            SysHelpCategory | None: 分类行；不存在为 None。
        """
        statement = select(SysHelpCategory).where(
            SysHelpCategory.id == category_id,
            SysHelpCategory.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def find_category(
        self, *, parent_id: int, name: str, exclude_id: int | None = None
    ) -> SysHelpCategory | None:
        """按父级与名称取分类（同级同名判定）。

        Args:
            parent_id: 上级分类 ID（0 = 根）。
            name: 分类名。
            exclude_id: 排除的分类主键（编辑自身时传）。

        Returns:
            SysHelpCategory | None: 命中行；无冲突为 None。
        """
        statement = (
            select(SysHelpCategory)
            .where(SysHelpCategory.parent_id == parent_id)
            .where(SysHelpCategory.name == name)
            .where(SysHelpCategory.deleted_at.is_(None))
        )
        if exclude_id is not None:
            statement = statement.where(SysHelpCategory.id != exclude_id)
        return (await self._session.execute(statement)).scalars().first()

    async def create_category(self, *, name: str, parent_id: int, sort: int, status: str) -> SysHelpCategory:
        """新建分类（调用方负责事务）。

        Args:
            name: 分类名。
            parent_id: 上级分类 ID（0 = 根）。
            sort: 同级排序。
            status: 状态。

        Returns:
            SysHelpCategory: 新行。
        """
        row = SysHelpCategory(parent_id=parent_id, name=name, sort=sort, status=status)
        self._session.add(row)
        await self._session.flush()
        return row

    async def save_category(self, row: SysHelpCategory) -> None:
        """落库分类改动（调用方负责事务）。

        Args:
            row: 分类行。
        """
        await self._session.flush()

    async def count_articles_by_category(self) -> ConcurrentStableDict[int, ConcurrentStableDict[str, int]]:
        """按分类统计未软删文章数（total / published / draft / offline）。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableDict[str, int]]: 分类主键 → 各状态计数。
        """
        statement = (
            select(
                SysHelpArticle.category_id,
                SysHelpArticle.status,
                func.count(),
            )
            .where(SysHelpArticle.deleted_at.is_(None))
            .group_by(SysHelpArticle.category_id, SysHelpArticle.status)
        )
        grouped: ConcurrentStableDict[int, ConcurrentStableDict[str, int]] = ConcurrentStableDict()
        for category_id, status, count in (await self._session.execute(statement)).all():
            bucket = grouped.get(int(category_id))
            if bucket is None:
                bucket = ConcurrentStableDict({"total": 0, "published": 0, "draft": 0, "offline": 0})
                grouped.set(int(category_id), bucket)
            key = str(status)
            bucket.set(key, bucket.get(key, 0) + int(count))
            bucket.set("total", bucket.get("total", 0) + int(count))
        return grouped

    async def list_articles_in_categories(
        self, category_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[SysHelpArticle]:
        """取若干分类下未软删文章（级联下架用）。

        Args:
            category_ids: 分类主键。

        Returns:
            ConcurrentStableList[SysHelpArticle]: 文章行。
        """
        if not category_ids:
            return ConcurrentStableList()
        statement = select(SysHelpArticle).where(
            SysHelpArticle.category_id.in_(list(category_ids)),
            SysHelpArticle.deleted_at.is_(None),
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def soft_delete_categories(self, rows: ConcurrentStableList[SysHelpCategory]) -> None:
        """软删除一批分类。

        Args:
            rows: 分类行。
        """
        for row in rows:
            row.soft_delete()
        await self._session.flush()

    # ---- 文章 ----

    async def list_articles(
        self,
        filters: HelpArticleFilters,
        *,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[SysHelpArticle], int]:
        """管理面文章列表（未软删；固定序 `updated_at DESC, id DESC`）。

        Args:
            filters: 筛选条件。
            offset: 偏移量。
            limit: 条数。

        Returns:
            tuple[ConcurrentStableList[SysHelpArticle], int]: 文章行与总数。
        """
        statement = select(SysHelpArticle).where(SysHelpArticle.deleted_at.is_(None))
        count_statement = select(func.count()).select_from(SysHelpArticle).where(SysHelpArticle.deleted_at.is_(None))
        if filters.category_id is not None:
            statement = statement.where(SysHelpArticle.category_id == filters.category_id)
            count_statement = count_statement.where(SysHelpArticle.category_id == filters.category_id)
        if filters.status is not None:
            statement = statement.where(SysHelpArticle.status == filters.status)
            count_statement = count_statement.where(SysHelpArticle.status == filters.status)
        if filters.source is not None:
            statement = statement.where(SysHelpArticle.source == filters.source)
            count_statement = count_statement.where(SysHelpArticle.source == filters.source)
        if filters.keyword:
            statement = statement.where(SysHelpArticle.title.contains(filters.keyword, autoescape=True))
            count_statement = count_statement.where(SysHelpArticle.title.contains(filters.keyword, autoescape=True))
        statement = statement.order_by(SysHelpArticle.updated_at.desc(), SysHelpArticle.id.desc())
        statement = statement.offset(offset).limit(limit)
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def get_article(self, article_id: int) -> SysHelpArticle | None:
        """按主键取未软删文章。

        Args:
            article_id: 文章主键。

        Returns:
            SysHelpArticle | None: 文章行；不存在为 None。
        """
        statement = select(SysHelpArticle).where(
            SysHelpArticle.id == article_id,
            SysHelpArticle.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def get_published_article(self, article_id: int) -> SysHelpArticle | None:
        """按主键取读者面可见文章（已发布 + 未软删）。

        Args:
            article_id: 文章主键。

        Returns:
            SysHelpArticle | None: 文章行；不可见为 None。
        """
        statement = select(SysHelpArticle).where(
            SysHelpArticle.id == article_id,
            SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
            SysHelpArticle.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def create_article(
        self,
        *,
        category_id: int,
        title: str,
        content: str,
        status: str,
        is_top: bool,
        author_id: int | None,
        generated_by: str,
        ai_model: str | None,
        reviewed_by: str | None,
        publish_now: bool,
    ) -> SysHelpArticle:
        """新建租户自建文章（调用方负责事务）。

        Args:
            category_id: 分类主键。
            title: 默认语言标题。
            content: 默认语言正文。
            status: 状态。
            is_top: 是否置顶。
            author_id: 作者主键。
            generated_by: 生成方式。
            ai_model: AI 模型。
            reviewed_by: 审核人。
            publish_now: 是否首次发布（写 `publish_at`）。

        Returns:
            SysHelpArticle: 新行。
        """
        row = SysHelpArticle(
            category_id=category_id,
            title=title,
            content=content,
            status=status,
            is_top=is_top,
            source="tenant",
            local_override=False,
            generated_by=generated_by,
            ai_model=ai_model,
            reviewed_by=reviewed_by,
            author_id=author_id,
            publish_at=datetime.now(UTC).replace(tzinfo=None, microsecond=0) if publish_now else None,
            view_count=0,
            helpful_count=0,
            unhelpful_count=0,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def save_article(self, row: SysHelpArticle) -> None:
        """落库文章改动（调用方负责事务）。

        Args:
            row: 文章行。
        """
        await self._session.flush()

    async def soft_delete_article(self, row: SysHelpArticle) -> None:
        """软删除文章并连带软删多语言与目标行。

        Args:
            row: 文章行。
        """
        article_id = int(row.id)
        for model in (SysHelpArticleI18n, SysHelpArticleTarget):
            statement = select(model).where(model.article_id == article_id, model.deleted_at.is_(None))
            for child in (await self._session.execute(statement)).scalars().all():
                child.soft_delete()
        row.soft_delete()
        await self._session.flush()

    async def count_published_tenant_on_target(
        self,
        *,
        target_type: str,
        target_key: str,
        exclude_article_id: int,
    ) -> int:
        """统计同目标上其它已发布的租户自建文章数（目标唯一性校验）。

        Args:
            target_type: 目标类型。
            target_key: 目标键。
            exclude_article_id: 排除的文章主键。

        Returns:
            int: 占用数。
        """
        statement = (
            select(func.count())
            .select_from(SysHelpArticleTarget)
            .join(SysHelpArticle, SysHelpArticle.id == SysHelpArticleTarget.article_id)
            .where(
                SysHelpArticleTarget.target_type == target_type,
                SysHelpArticleTarget.target_key == target_key,
                SysHelpArticleTarget.deleted_at.is_(None),
                SysHelpArticle.source == ARTICLE_SOURCE_TENANT,
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
                SysHelpArticle.id != exclude_article_id,
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    # ---- 读者面 ----

    async def list_published(
        self,
        *,
        category_ids: ConcurrentStableList[int] | None,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[SysHelpArticle], int]:
        """读者面文章列表（已发布 + 分类启用；置顶优先）。

        Args:
            category_ids: 分类范围（None 表示全部；空清单直接返回空）。
            offset: 偏移量。
            limit: 条数。

        Returns:
            tuple[ConcurrentStableList[SysHelpArticle], int]: 文章行与总数。
        """
        if category_ids is not None and not category_ids:
            return ConcurrentStableList(), 0
        base = (
            select(SysHelpArticle)
            .join(SysHelpCategory, SysHelpCategory.id == SysHelpArticle.category_id)
            .where(
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
                SysHelpCategory.status == _CATEGORY_STATUS_ENABLED,
                SysHelpCategory.deleted_at.is_(None),
            )
        )
        count_statement = (
            select(func.count())
            .select_from(SysHelpArticle)
            .join(SysHelpCategory, SysHelpCategory.id == SysHelpArticle.category_id)
            .where(
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
                SysHelpCategory.status == _CATEGORY_STATUS_ENABLED,
                SysHelpCategory.deleted_at.is_(None),
            )
        )
        if category_ids is not None:
            base = base.where(SysHelpArticle.category_id.in_(list(category_ids)))
            count_statement = count_statement.where(SysHelpArticle.category_id.in_(list(category_ids)))
        statement = (
            base.order_by(
                SysHelpArticle.is_top.desc(),
                SysHelpArticle.publish_at.desc(),
                SysHelpArticle.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def list_enabled_categories(self) -> ConcurrentStableList[SysHelpCategory]:
        """取启用且未软删分类（读者树）。

        Returns:
            ConcurrentStableList[SysHelpCategory]: 分类行。
        """
        statement = (
            select(SysHelpCategory)
            .where(SysHelpCategory.status == _CATEGORY_STATUS_ENABLED, SysHelpCategory.deleted_at.is_(None))
            .order_by(SysHelpCategory.sort, SysHelpCategory.id)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_published_by_category(self) -> ConcurrentStableDict[int, int]:
        """按分类统计已发布文章数（未软删）。

        Returns:
            ConcurrentStableDict[int, int]: 分类主键 → 已发布数。
        """
        statement = (
            select(SysHelpArticle.category_id, func.count())
            .where(
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
            )
            .group_by(SysHelpArticle.category_id)
        )
        counts: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        for category_id, count in (await self._session.execute(statement)).all():
            counts.set(int(category_id), int(count))
        return counts

    # ---- 反馈与计数 ----

    async def get_feedback(self, *, article_id: int, user_id: int) -> SysHelpFeedback | None:
        """取某用户对某文章的反馈（未软删）。

        Args:
            article_id: 文章主键。
            user_id: 用户主键。

        Returns:
            SysHelpFeedback | None: 反馈行；未投为 None。
        """
        statement = select(SysHelpFeedback).where(
            SysHelpFeedback.article_id == article_id,
            SysHelpFeedback.user_id == user_id,
            SysHelpFeedback.deleted_at.is_(None),
        )
        return (await self._session.execute(statement)).scalars().first()

    async def upsert_feedback(
        self,
        *,
        article_id: int,
        user_id: int,
        feedback: str,
        comment: str | None,
    ) -> tuple[SysHelpFeedback, str | None]:
        """写入 / 改投反馈（同用户同文章唯一）。

        Args:
            article_id: 文章主键。
            user_id: 用户主键。
            feedback: 反馈类型。
            comment: 评论（可空）。

        Returns:
            tuple[SysHelpFeedback, str | None]: 反馈行与原反馈类型（首次为 None）。
        """
        row = await self.get_feedback(article_id=article_id, user_id=user_id)
        if row is None:
            created = SysHelpFeedback(article_id=article_id, user_id=user_id, feedback=feedback, comment=comment)
            self._session.add(created)
            await self._session.flush()
            return created, None
        previous = str(row.feedback)
        row.feedback = feedback
        row.comment = comment
        await self._session.flush()
        return row, previous

    async def bump_counters(
        self,
        article_id: int,
        *,
        view: int = 0,
        helpful: int = 0,
        unhelpful: int = 0,
    ) -> None:
        """按增量更新文章计数（单条 UPDATE，不加载 ORM 行）。

        Args:
            article_id: 文章主键。
            view: 阅读增量。
            helpful: 有帮助增量（可为负）。
            unhelpful: 无帮助增量（可为负）。
        """
        if view:
            await self._session.execute(
                update(SysHelpArticle)
                .where(SysHelpArticle.id == article_id)
                .values(view_count=SysHelpArticle.view_count + view)
                .execution_options(synchronize_session=False)
            )
        if helpful:
            await self._session.execute(
                update(SysHelpArticle)
                .where(SysHelpArticle.id == article_id)
                .values(helpful_count=SysHelpArticle.helpful_count + helpful)
                .execution_options(synchronize_session=False)
            )
        if unhelpful:
            await self._session.execute(
                update(SysHelpArticle)
                .where(SysHelpArticle.id == article_id)
                .values(unhelpful_count=SysHelpArticle.unhelpful_count + unhelpful)
                .execution_options(synchronize_session=False)
            )

    # ---- 统计 ----

    async def article_stats(
        self,
        filters: HelpArticleFilters,
        *,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[ArticleStatRow], int]:
        """统计视图明细（按文章，固定序：阅读量倒序 → 主键倒序）。

        Args:
            filters: 筛选条件。
            offset: 偏移量。
            limit: 条数。

        Returns:
            tuple[ConcurrentStableList[ArticleStatRow], int]: 明细与总数。
        """
        statement = select(SysHelpArticle).where(SysHelpArticle.deleted_at.is_(None))
        count_statement = select(func.count()).select_from(SysHelpArticle).where(SysHelpArticle.deleted_at.is_(None))
        if filters.category_id is not None:
            statement = statement.where(SysHelpArticle.category_id == filters.category_id)
            count_statement = count_statement.where(SysHelpArticle.category_id == filters.category_id)
        if filters.keyword:
            statement = statement.where(SysHelpArticle.title.contains(filters.keyword, autoescape=True))
            count_statement = count_statement.where(SysHelpArticle.title.contains(filters.keyword, autoescape=True))
        statement = (
            statement.order_by(SysHelpArticle.view_count.desc(), SysHelpArticle.id.desc()).offset(offset).limit(limit)
        )
        rows = ConcurrentStableList(
            ArticleStatRow(
                article_id=int(row.id),
                title=str(row.title),
                category_id=int(row.category_id),
                status=str(row.status),
                view_count=int(row.view_count),
                helpful_count=int(row.helpful_count),
                unhelpful_count=int(row.unhelpful_count),
            )
            for row in (await self._session.execute(statement)).scalars().all()
        )
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def category_stats(self) -> ConcurrentStableList[CategoryStatRow]:
        """统计视图明细（按分类，直接归属；排序由调用方处理）。

        Returns:
            ConcurrentStableList[CategoryStatRow]: 分类聚合行。
        """
        published_flag = case((SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED, 1), else_=0)
        statement = (
            select(
                SysHelpArticle.category_id,
                func.count(),
                func.sum(published_flag),
                func.coalesce(func.sum(SysHelpArticle.view_count), 0),
                func.coalesce(func.sum(SysHelpArticle.helpful_count), 0),
                func.coalesce(func.sum(SysHelpArticle.unhelpful_count), 0),
            )
            .where(SysHelpArticle.deleted_at.is_(None))
            .group_by(SysHelpArticle.category_id)
        )
        return ConcurrentStableList(
            CategoryStatRow(
                category_id=int(category_id),
                article_count=int(article_count),
                published_count=int(published_count),
                view_count=int(view_count),
                helpful_count=int(helpful_count),
                unhelpful_count=int(unhelpful_count),
            )
            for category_id, article_count, published_count, view_count, helpful_count, unhelpful_count in (
                await self._session.execute(statement)
            ).all()
        )

    async def status_summary(self) -> ConcurrentStableList[StatusSummaryRow]:
        """统计汇总（按状态分桶）。

        Returns:
            ConcurrentStableList[StatusSummaryRow]: 状态分桶行。
        """
        statement = (
            select(
                SysHelpArticle.status,
                func.count(),
                func.coalesce(func.sum(SysHelpArticle.view_count), 0),
                func.coalesce(func.sum(SysHelpArticle.helpful_count), 0),
                func.coalesce(func.sum(SysHelpArticle.unhelpful_count), 0),
            )
            .where(SysHelpArticle.deleted_at.is_(None))
            .group_by(SysHelpArticle.status)
        )
        return ConcurrentStableList(
            StatusSummaryRow(
                status=str(status),
                article_count=int(article_count),
                view_count=int(view_count),
                helpful_count=int(helpful_count),
                unhelpful_count=int(unhelpful_count),
            )
            for status, article_count, view_count, helpful_count, unhelpful_count in (
                await self._session.execute(statement)
            ).all()
        )

    # ---- 包列表 ----

    async def list_packages(
        self,
        *,
        product_key: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> tuple[ConcurrentStableList[SysHelpPackage], int]:
        """帮助包登记列表（未软删；固定序：装载时间倒序 → 主键倒序）。

        Args:
            product_key: 产品键筛选。
            status: 包状态筛选。
            offset: 偏移量。
            limit: 条数。

        Returns:
            tuple[ConcurrentStableList[SysHelpPackage], int]: 包行与总数。
        """
        statement = select(SysHelpPackage).where(SysHelpPackage.deleted_at.is_(None))
        count_statement = select(func.count()).select_from(SysHelpPackage).where(SysHelpPackage.deleted_at.is_(None))
        if product_key is not None:
            statement = statement.where(SysHelpPackage.product_key == product_key)
            count_statement = count_statement.where(SysHelpPackage.product_key == product_key)
        if status is not None:
            statement = statement.where(SysHelpPackage.status == status)
            count_statement = count_statement.where(SysHelpPackage.status == status)
        statement = (
            statement.order_by(SysHelpPackage.loaded_at.desc(), SysHelpPackage.id.desc()).offset(offset).limit(limit)
        )
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total
