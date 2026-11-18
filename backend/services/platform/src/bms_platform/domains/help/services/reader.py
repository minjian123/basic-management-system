"""帮助读者面服务：分类树 / 文章列表 / 详情 / 反馈（12_01）。

- **可见性**：只返回已发布且未软删文章；列表额外要求分类启用，详情不检查分类状态（分类停用不使旧链接失效）；
- **阅读计数**：详情 +1，同用户同文章 60 秒内只计一次（缓存窗口；不可用降级按次并告警）；
- **反馈**：同用户同文章唯一、可改投；文章表两侧计数按差值增减（单条 UPDATE）；
- **语言**：按「请求语言 → 租户默认语言 → 主表快照」三级回退（列表与详情同口径）。
"""

from __future__ import annotations

import re

from bms_core.cache.base import CacheRegion, build_cache_key
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.context import get_current_tenant
from bms_core.core.exceptions import (
    BizError,
    HelpArticleNotFoundError,
    HelpFeedbackInvalidError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.help.values import FEEDBACK_HELPFUL, FEEDBACK_UNHELPFUL, FEEDBACK_VALUES
from bms_core.i18n.rules import normalize_locale
from bms_core.models.platform.help import SysHelpArticle, SysHelpCategory
from bms_platform.domains.help.constants import (
    MAX_READER_SUMMARY_CHARS,
    VIEW_COUNT_DEDUP_TTL,
)
from bms_platform.domains.help.repositories.maintenance import HelpArticleMaintenanceRepository
from bms_platform.domains.help.schemas.feedback import HelpFeedbackRequest, HelpFeedbackResult
from bms_platform.domains.help.schemas.reader import (
    HelpReaderArticleDetail,
    HelpReaderArticleItem,
    HelpReaderArticlePage,
    HelpReaderCategoryNode,
    HelpReaderCategoryTree,
)

__all__ = ["HelpReaderService"]

_LOGGER = get_logger("bms.help")

_HELP_CACHE_DOMAIN = "help"
"""帮助内容缓存域（与 `bms_core.help.cache` 同域）。"""

_TAG_PATTERN = re.compile(r"<[^>]*>")
"""去标签正则（仅用于列表摘要，不参与净化）。"""


class HelpReaderService(BaseFrameworkObject):
    """帮助读者面服务。"""

    def __init__(
        self,
        *,
        session: DbSession,
        uow: UnitOfWork,
        cache: CacheRegion,
        locale: str,
        default_locale: str,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            uow: 请求级工作单元（阅读计数 / 反馈写事务）。
            cache: 缓存 Region（阅读计数去重窗口）。
            locale: 请求语言标识。
            default_locale: 租户默认语言（请求语言缺行时回退）。
        """
        self._session = session
        self._uow = uow
        self._cache = cache
        self._locale = normalize_locale(locale)
        self._default_locale = normalize_locale(default_locale)
        self._repo = HelpArticleMaintenanceRepository(session)
        self._tenant = get_current_tenant()

    async def list_categories(self) -> HelpReaderCategoryTree:
        """读者面分类树（启用分类 + 已发布文章数含子孙）。

        Returns:
            HelpReaderCategoryTree: 分类树。
        """
        rows = await self._repo.list_enabled_categories()
        counts = await self._repo.count_published_by_category()
        roots = self._category_nodes(rows, counts, parent_id=0)
        return HelpReaderCategoryTree(items=roots, total=len(rows))

    def _category_nodes(
        self,
        rows: ConcurrentStableList[SysHelpCategory],
        counts: ConcurrentStableDict[int, int],
        *,
        parent_id: int,
    ) -> ConcurrentStableList[HelpReaderCategoryNode]:
        """递归构造读者面分类节点（子树已发布数聚合）。

        Args:
            rows: 启用分类行。
            counts: 分类主键 → 已发布数。
            parent_id: 当前父级。

        Returns:
            ConcurrentStableList[HelpReaderCategoryNode]: 该父级下的节点。
        """
        children = ConcurrentStableList(
            row
            for row in ConcurrentStableList(rows).sorted(key=lambda item: (item.sort, item.id))
            if int(row.parent_id) == parent_id
        )
        nodes: ConcurrentStableList[HelpReaderCategoryNode] = ConcurrentStableList()
        for row in children:
            child_nodes = self._category_nodes(rows, counts, parent_id=int(row.id))
            published = counts.get(int(row.id), 0)
            subtree = published + sum(node.subtree_published_count for node in child_nodes)
            nodes.add(
                HelpReaderCategoryNode(
                    id=int(row.id),
                    name=str(row.name),
                    sort=int(row.sort),
                    published_count=published,
                    subtree_published_count=subtree,
                    children=child_nodes,
                )
            )
        return nodes

    async def list_articles(self, *, category_id: int | None, page: int, size: int) -> HelpReaderArticlePage:
        """读者面文章列表（仅已发布 + 分类启用；置顶优先）。

        Args:
            category_id: 分类主键（含子孙；None 表示全部）。
            page: 页码。
            size: 每页条数。

        Returns:
            HelpReaderArticlePage: 分页结果。
        """
        category_ids: ConcurrentStableList[int] | None = None
        categories = await self._repo.list_enabled_categories()
        if category_id is not None:
            category_ids = self._subtree_ids(categories, category_id)
        articles, total = await self._repo.list_published(
            category_ids=category_ids,
            offset=(page - 1) * size,
            limit=size,
        )
        paths = self._repo.content.build_path_map(categories)
        texts = await self._repo.content.load_article_i18n(
            ConcurrentStableList(int(article.id) for article in articles)
        )
        items = ConcurrentStableList(self._item(article, paths, texts.get(int(article.id))) for article in articles)
        return HelpReaderArticlePage(list=items, total=total, page=page, size=size)

    async def get_article(self, article_id: int, *, user_id: int) -> HelpReaderArticleDetail:
        """读者面文章详情（阅读计数 +1 + 我的反馈）。

        Args:
            article_id: 文章主键。
            user_id: 当前用户主键。

        Returns:
            HelpReaderArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在或不可见（`40016`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._require_published(article_id)
            counted = await self.should_count_view(user_id=user_id, article_id=article_id)
            if counted:
                await self._repo.bump_counters(article_id, view=1)
            feedback = await self._repo.get_feedback(article_id=article_id, user_id=user_id)
            categories = await self._repo.list_enabled_categories()
            texts = await self._repo.content.load_article_i18n(ConcurrentStableList((article_id,)))
            title, content = self._localized(row, texts.get(article_id))
            return HelpReaderArticleDetail(
                id=int(row.id),
                title=title,
                content=content,
                category_id=int(row.category_id),
                category_path=self._repo.content.build_path_map(categories).get(int(row.category_id), ""),
                publish_at=row.publish_at,
                view_count=int(row.view_count) + (1 if counted else 0),
                helpful_count=int(row.helpful_count),
                unhelpful_count=int(row.unhelpful_count),
                my_feedback=str(feedback.feedback) if feedback is not None else None,
            )

    async def submit_feedback(
        self, article_id: int, *, user_id: int, payload: HelpFeedbackRequest
    ) -> HelpFeedbackResult:
        """提交 / 改投反馈。

        Args:
            article_id: 文章主键。
            user_id: 当前用户主键。
            payload: 反馈请求。

        Returns:
            HelpFeedbackResult: 反馈结果（含最新计数）。

        Raises:
            HelpArticleNotFoundError: 文章不存在或不可见（`40016`）。
            HelpFeedbackInvalidError: 反馈类型 / 评论非法（`40020`）。
        """
        feedback = payload.feedback.strip()
        if feedback not in FEEDBACK_VALUES:
            raise HelpFeedbackInvalidError(f"反馈类型非法：{payload.feedback}")
        comment = (payload.comment or "").strip() or None
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._require_published(article_id)
            _row, previous = await self._repo.upsert_feedback(
                article_id=article_id,
                user_id=user_id,
                feedback=feedback,
                comment=comment,
            )
            helpful_delta, unhelpful_delta = _feedback_delta(previous=previous, current=feedback)
            if helpful_delta or unhelpful_delta:
                await self._repo.bump_counters(article_id, helpful=helpful_delta, unhelpful=unhelpful_delta)
            return HelpFeedbackResult(
                feedback=feedback,
                comment=comment,
                helpful_count=max(0, int(row.helpful_count) + helpful_delta),
                unhelpful_count=max(0, int(row.unhelpful_count) + unhelpful_delta),
                changed=previous != feedback,
            )

    async def _require_published(self, article_id: int) -> SysHelpArticle:
        """取读者面可见文章或抛 40016。

        Args:
            article_id: 文章主键。

        Returns:
            SysHelpArticle: 文章行。

        Raises:
            HelpArticleNotFoundError: 文章不存在或不可见（`40016`）。
        """
        row = await self._repo.get_published_article(article_id)
        if row is None:
            raise HelpArticleNotFoundError(f"文章不存在或不可见：{article_id}")
        return row

    async def should_count_view(self, *, user_id: int, article_id: int) -> bool:
        """判断本次阅读是否计数（60 秒窗口去重；缓存不可用按次计）。

        Args:
            user_id: 用户主键。
            article_id: 文章主键。

        Returns:
            bool: 是否计数。
        """
        key = build_cache_key(
            tenant=self._tenant,
            domain=_HELP_CACHE_DOMAIN,
            business_key=f"view:{user_id}:{article_id}",
        )
        try:
            seen = await self._cache.aget(key)
            if seen is not None:
                return False
            await self._cache.aset(key, 1, VIEW_COUNT_DEDUP_TTL)
        except (BizError, OSError) as exc:
            _LOGGER.warning("help_view_dedup_unavailable", error=str(exc))
        return True

    def _subtree_ids(self, rows: ConcurrentStableList[SysHelpCategory], root_id: int) -> ConcurrentStableList[int]:
        """取分类子树主键（含自身；停用分类的子节点自然不出现）。

        Args:
            rows: 启用分类行。
            root_id: 根分类主键。

        Returns:
            ConcurrentStableList[int]: 子树主键。
        """
        children: ConcurrentStableDict[int, ConcurrentStableList[int]] = ConcurrentStableDict()
        enabled_ids: ConcurrentStableList[int] = ConcurrentStableList(int(row.id) for row in rows)
        if root_id not in enabled_ids:
            return ConcurrentStableList()
        for row in rows:
            bucket = children.get(int(row.parent_id))
            if bucket is None:
                bucket = ConcurrentStableList[int]()
                children.set(int(row.parent_id), bucket)
            bucket.add(int(row.id))
        collected: ConcurrentStableList[int] = ConcurrentStableList()
        pending: ConcurrentStableList[int] = ConcurrentStableList((root_id,))
        while pending:
            current = pending.pop()
            if current in collected:  # pragma: no cover - 分类写入已拒绝成环，仅防御存量脏数据
                continue
            collected.add(current)
            pending.extend(children.get(current) or ConcurrentStableList[int]())
        return collected

    def _item(
        self,
        row: SysHelpArticle,
        paths: ConcurrentStableDict[int, str],
        text: ConcurrentStableFrozenDict[str, tuple[str, str]] | None,
    ) -> HelpReaderArticleItem:
        """文章行 → 读者面列表行。

        Args:
            row: 文章行。
            paths: 分类路径映射。
            text: 语言 → (标题, 正文) 映射。

        Returns:
            HelpReaderArticleItem: 列表行。
        """
        title, content = self._localized(row, text)
        return HelpReaderArticleItem(
            id=int(row.id),
            title=title,
            summary=summary_of(content),
            category_id=int(row.category_id),
            category_path=paths.get(int(row.category_id), ""),
            is_top=bool(row.is_top),
            publish_at=row.publish_at,
            view_count=int(row.view_count),
            helpful_count=int(row.helpful_count),
            unhelpful_count=int(row.unhelpful_count),
        )

    def _localized(
        self,
        row: SysHelpArticle,
        text: ConcurrentStableFrozenDict[str, tuple[str, str]] | None,
    ) -> tuple[str, str]:
        """取当前语言文案（请求语言 → 默认语言 → 主表快照）。

        Args:
            row: 文章行。
            text: 语言 → (标题, 正文) 映射（已归一）。

        Returns:
            tuple[str, str]: （标题, 正文）。
        """
        if text is None:
            return str(row.title), str(row.content)
        for code in (self._locale, self._default_locale):
            entry = text.get(code)
            if entry is not None:
                title, content = entry
                return title or str(row.title), content or str(row.content)
        return str(row.title), str(row.content)


def _feedback_delta(*, previous: str | None, current: str) -> tuple[int, int]:
    """计算反馈改投的计数增量。

    Args:
        previous: 原反馈类型（None 表示首次）。
        current: 新反馈类型。

    Returns:
        tuple[int, int]: （有帮助增量, 无帮助增量）。
    """
    if previous == current:
        return 0, 0
    helpful = (1 if current == FEEDBACK_HELPFUL else 0) - (1 if previous == FEEDBACK_HELPFUL else 0)
    unhelpful = (1 if current == FEEDBACK_UNHELPFUL else 0) - (1 if previous == FEEDBACK_UNHELPFUL else 0)
    return helpful, unhelpful


def summary_of(content: str) -> str:
    """正文去标签并截断为列表摘要。

    Args:
        content: 正文 HTML。

    Returns:
        str: 摘要文本。
    """
    if not content:
        return ""
    text = _TAG_PATTERN.sub("", content).replace("&nbsp;", " ")
    trimmed = " ".join(text.split())
    if len(trimmed) <= MAX_READER_SUMMARY_CHARS:
        return trimmed
    return trimmed[:MAX_READER_SUMMARY_CHARS] + "…"
