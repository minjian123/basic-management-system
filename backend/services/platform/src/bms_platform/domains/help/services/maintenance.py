"""帮助内容管理面服务：分类 / 文章维护编排（12_01）。

- **事务**：写方法统一 `uow.begin()`，读校验 + 落库 + 事件入发件箱 + 缓存版本递增同事务；
- **正文**：每个语言独立经 `richtext.sanitize.sanitize_html` 权威清洗；默认语言快照落主表；
- **状态机**：新建默认草稿；发布 / 下架只允许合法迁移；编辑显式状态、缺省沿用；
- **包来源文章**：编辑自动置 `local_override=true`；删除拒绝（引导下架）；
- **事件**：发布 / 更新 / 删除经发件箱发布 `sys.help.article.*`（草稿变更不发）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.context import get_current_tenant, get_current_user_id
from bms_core.core.exceptions import (
    HelpAnchorUnresolvedError,
    HelpArticleContentInvalidError,
    HelpArticleNotFoundError,
    HelpArticleStateInvalidError,
    HelpArticleTargetConflictError,
    HelpCategoryInvalidError,
    HelpCategoryNotEmptyError,
    HelpCategoryNotFoundError,
    HelpLocaleUnsupportedError,
    ParamError,
)
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.help.anchors import HelpAnchorKind
from bms_core.help.cache import bump_content_version
from bms_core.help.values import (
    ARTICLE_SOURCE_TENANT,
    ARTICLE_STATUS_DRAFT,
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
    ARTICLE_STATUSES,
    GENERATED_BY_AI,
    GENERATED_BY_MANUAL,
    GENERATED_BY_VALUES,
    TARGET_TYPE_GLOBAL,
)
from bms_core.i18n.rules import normalize_locale
from bms_core.models.platform.help import SysHelpArticle, SysHelpCategory
from bms_core.outbox.base import BaseOutboxStore
from bms_core.repositories.help_anchor import load_help_anchor_kinds
from bms_core.repositories.help_locale import load_help_default_locale, load_help_locales
from bms_core.richtext.sanitize import html_text_length, sanitize_html
from bms_platform.domains.help.constants import (
    MAX_ARTICLE_CONTENT_BYTES,
    MAX_CATEGORY_DEPTH,
)
from bms_platform.domains.help.repositories.maintenance import (
    HelpArticleFilters,
    HelpArticleMaintenanceRepository,
)
from bms_platform.domains.help.schemas.article import (
    HelpManageArticleCreate,
    HelpManageArticleDeleteResult,
    HelpManageArticleDetail,
    HelpManageArticleItem,
    HelpManageArticlePage,
    HelpManageArticleUpdate,
    HelpManageLocaleText,
    HelpManageTargetItem,
)
from bms_platform.domains.help.schemas.category import (
    HelpManageCategoryCreate,
    HelpManageCategoryDeleteResult,
    HelpManageCategoryNode,
    HelpManageCategoryTree,
    HelpManageCategoryUpdate,
)
from bms_platform.domains.help.targets import is_known_target_type, target_key_matches, target_problem

__all__ = ["ARTICLE_DELETED_EVENT", "ARTICLE_PUBLISHED_EVENT", "ARTICLE_UPDATED_EVENT", "HelpMaintenanceService"]

_LOGGER = get_logger("bms.help")

ARTICLE_PUBLISHED_EVENT = "sys.help.article.published"
"""帮助文章发布事件（契约已登记）。"""

ARTICLE_UPDATED_EVENT = "sys.help.article.updated"
"""帮助文章更新 / 下架事件（契约已登记）。"""

ARTICLE_DELETED_EVENT = "sys.help.article.deleted"
"""帮助文章删除事件（契约已登记）。"""

_CATEGORY_STATUSES: ConcurrentStableFrozenList[str] = ConcurrentStableFrozenList(("enabled", "disabled"))
"""分类状态值域。"""


class HelpMaintenanceService(BaseFrameworkObject):
    """帮助内容管理面服务（分类 / 文章）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        platform_session: DbSession,
        uow: UnitOfWork,
        outbox: BaseOutboxStore,
        cache: CacheRegion,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话（内容表）。
            platform_session: 平台库会话（锚点清单）。
            uow: 请求级工作单元（事务边界）。
            outbox: 发件箱存储（事件发布）。
            cache: 缓存 Region（内容版本键）。
        """
        self._session = session
        self._platform_session = platform_session
        self._uow = uow
        self._outbox = outbox
        self._cache = cache
        self._repo = HelpArticleMaintenanceRepository(session)
        self._tenant = get_current_tenant()

    # ------------------------------------------------------------------ 分类

    async def list_categories(self) -> HelpManageCategoryTree:
        """管理面分类树（含停用与各状态计数）。

        Returns:
            HelpManageCategoryTree: 分类树。
        """
        rows = await self._repo.list_categories()
        counts = await self._repo.count_articles_by_category()
        roots, total = self._build_category_tree(rows, counts)
        return HelpManageCategoryTree(items=roots, total=total)

    def _build_category_tree(
        self,
        rows: ConcurrentStableList[SysHelpCategory],
        counts: ConcurrentStableDict[int, ConcurrentStableDict[str, int]],
    ) -> tuple[ConcurrentStableList[HelpManageCategoryNode], int]:
        """把扁平分类行拼成树（含子树计数）。

        Args:
            rows: 分类行。
            counts: 分类主键 → 各状态计数。

        Returns:
            tuple[ConcurrentStableList[HelpManageCategoryNode], int]: 根节点与节点总数。
        """
        children: ConcurrentStableDict[int, ConcurrentStableList[SysHelpCategory]] = ConcurrentStableDict()
        for row in rows:
            bucket = children.get(int(row.parent_id))
            if bucket is None:
                bucket = ConcurrentStableList[SysHelpCategory]()
                children.set(int(row.parent_id), bucket)
            bucket.add(row)
        ordered: ConcurrentStableList[SysHelpCategory] = ConcurrentStableList(rows)
        roots = ConcurrentStableList(
            self._category_node(row, children, counts)
            for row in ordered.sorted(key=lambda item: (item.sort, item.id))
            if int(row.parent_id) == 0
        )
        return roots, len(rows)

    def _category_node(
        self,
        row: SysHelpCategory,
        children: ConcurrentStableDict[int, ConcurrentStableList[SysHelpCategory]],
        counts: ConcurrentStableDict[int, ConcurrentStableDict[str, int]],
    ) -> HelpManageCategoryNode:
        """构造单个分类节点（递归子节点与子树计数）。

        Args:
            row: 分类行。
            children: 父级 → 子分类行。
            counts: 分类主键 → 各状态计数。

        Returns:
            HelpManageCategoryNode: 分类节点。
        """
        bucket = counts.get(int(row.id)) or ConcurrentStableDict({"total": 0, "published": 0, "draft": 0, "offline": 0})
        child_rows = children.get(int(row.id)) or ConcurrentStableList[SysHelpCategory]()
        child_nodes = ConcurrentStableList(
            self._category_node(child, children, counts)
            for child in ConcurrentStableList(child_rows).sorted(key=lambda item: (item.sort, item.id))
        )
        subtree = int(bucket.get("total", 0)) + sum(node.subtree_article_count for node in child_nodes)
        return HelpManageCategoryNode(
            id=int(row.id),
            parent_id=int(row.parent_id),
            name=str(row.name),
            sort=int(row.sort),
            status=str(row.status),
            article_count=int(bucket.get("total", 0)),
            subtree_article_count=subtree,
            published_count=int(bucket.get("published", 0)),
            draft_count=int(bucket.get("draft", 0)),
            offline_count=int(bucket.get("offline", 0)),
            children=child_nodes,
        )

    async def create_category(self, payload: HelpManageCategoryCreate) -> HelpManageCategoryNode:
        """新建分类。

        Args:
            payload: 新建请求。

        Returns:
            HelpManageCategoryNode: 新节点。

        Raises:
            ParamError: 状态非法（`10001`）。
            HelpCategoryNotFoundError: 父级不存在（`40014`）。
            HelpCategoryInvalidError: 同级同名 / 深度超限（`40023`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            self._assert_category_status(payload.status)
            await self._assert_category_parent(int(payload.parent_id))
            await self._assert_category_name_free(int(payload.parent_id), payload.name)
            row = await self._repo.create_category(
                name=payload.name,
                parent_id=int(payload.parent_id),
                sort=payload.sort,
                status=payload.status,
            )
            await self._bump_cache()
            return await self._node_of(int(row.id))

    async def update_category(self, category_id: int, payload: HelpManageCategoryUpdate) -> HelpManageCategoryNode:
        """编辑分类。

        Args:
            category_id: 分类主键。
            payload: 编辑请求。

        Returns:
            HelpManageCategoryNode: 更新后的节点。

        Raises:
            HelpCategoryNotFoundError: 分类 / 父级不存在（`40014`）。
            ParamError: 状态非法（`10001`）。
            HelpCategoryInvalidError: 同级同名 / 成环 / 深度超限（`40023`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._category_or_raise(category_id)
            if payload.status is not None:
                self._assert_category_status(payload.status)
                row.status = payload.status
            if payload.parent_id is not None:
                parent_id = int(payload.parent_id)
                await self._assert_category_parent(parent_id, self_id=category_id)
                row.parent_id = parent_id
            if payload.name is not None and payload.name != row.name:
                await self._assert_category_name_free(int(row.parent_id), payload.name, exclude_id=category_id)
                row.name = payload.name
            if payload.sort is not None:
                row.sort = payload.sort
            await self._repo.save_category(row)
            await self._bump_cache()
            return await self._node_of(int(row.id))

    async def delete_category(self, category_id: int, *, cascade: bool) -> HelpManageCategoryDeleteResult:
        """删除分类（默认拒删；`cascade=true` 级联下架子树文章后软删）。

        Args:
            category_id: 分类主键。
            cascade: 是否级联处理。

        Returns:
            HelpManageCategoryDeleteResult: 删除计数。

        Raises:
            HelpCategoryNotFoundError: 分类不存在（`40014`）。
            HelpCategoryNotEmptyError: 存在子分类或文章且未级联（`40015`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            await self._category_or_raise(category_id)
            rows = await self._repo.list_categories()
            subtree = self._subtree_ids(rows, category_id)
            children_count = sum(1 for item in rows if int(item.parent_id) == category_id and int(item.id) in subtree)
            articles = await self._repo.list_articles_in_categories(subtree)
            if not cascade and (children_count or articles):
                raise HelpCategoryNotEmptyError(
                    "分类下存在子分类或文章，不能直接删除",
                    data={"child_count": children_count, "article_count": len(articles)},
                )
            offlined = 0
            for article in articles:
                if article.status != ARTICLE_STATUS_OFFLINE:
                    article.status = ARTICLE_STATUS_OFFLINE
                    offlined += 1
            targets = ConcurrentStableList(item for item in rows if int(item.id) in subtree)
            await self._repo.soft_delete_categories(targets)
            await self._bump_cache()
            return HelpManageCategoryDeleteResult(deleted_categories=len(targets), offlined_articles=offlined)

    def _subtree_ids(self, rows: ConcurrentStableList[SysHelpCategory], root_id: int) -> ConcurrentStableList[int]:
        """取分类子树主键（含自身；断链 / 环不影响）。

        Args:
            rows: 全部分类行。
            root_id: 根分类主键。

        Returns:
            ConcurrentStableList[int]: 子树主键。
        """
        children: ConcurrentStableDict[int, ConcurrentStableList[int]] = ConcurrentStableDict()
        for row in rows:
            bucket = children.get(int(row.parent_id))
            if bucket is None:
                bucket = ConcurrentStableList[int]()
                children.set(int(row.parent_id), bucket)
            bucket.add(int(row.id))
        collected: ConcurrentStableList[int] = ConcurrentStableList()
        pending: ConcurrentStableList[int] = ConcurrentStableList((root_id,))
        while pending:
            current = pending[0]
            pending.remove(current)
            if current in collected:  # pragma: no cover - 分类写入已拒绝成环，仅防御存量脏数据
                continue
            collected.add(current)
            for child_id in children.get(current) or ConcurrentStableList[int]():
                pending.add(child_id)
        return collected

    async def _node_of(self, category_id: int) -> HelpManageCategoryNode:
        """取分类在当前树中的节点（含子树计数）。

        Args:
            category_id: 分类主键。

        Returns:
            HelpManageCategoryNode: 分类节点。

        Raises:
            HelpCategoryNotFoundError: 分类不存在（`40014`）。
        """
        tree = await self.list_categories()
        pending: ConcurrentStableList[HelpManageCategoryNode] = ConcurrentStableList(tree.items)
        while pending:
            node = pending.pop()
            if int(node.id) == category_id:
                return node
            pending.extend(node.children)
        raise HelpCategoryNotFoundError(f"分类不存在：{category_id}")  # pragma: no cover - 事务内分类必然存在

    async def _category_or_raise(self, category_id: int) -> SysHelpCategory:
        """取分类或抛 40014。

        Args:
            category_id: 分类主键。

        Returns:
            SysHelpCategory: 分类行。

        Raises:
            HelpCategoryNotFoundError: 分类不存在（`40014`）。
        """
        row = await self._repo.get_category(category_id)
        if row is None:
            raise HelpCategoryNotFoundError(f"分类不存在：{category_id}")
        return row

    def _assert_category_status(self, status: str) -> None:
        """校验分类状态值域。

        Args:
            status: 状态。

        Raises:
            ParamError: 状态非法（`10001`）。
        """
        if status not in _CATEGORY_STATUSES:
            raise ParamError(f"分类状态非法：{status}")

    async def _assert_category_parent(self, parent_id: int, *, self_id: int | None = None) -> None:
        """校验父级存在、不成环、不超深度。

        Args:
            parent_id: 目标父级（0 = 根）。
            self_id: 编辑自身主键（新建为 None）。

        Raises:
            HelpCategoryNotFoundError: 父级不存在（`40014`）。
            HelpCategoryInvalidError: 成环 / 超深度（`40023`）。
        """
        if parent_id == 0:
            return
        parent = await self._repo.get_category(parent_id)
        if parent is None:
            raise HelpCategoryNotFoundError(f"上级分类不存在：{parent_id}")
        if self_id is not None and parent_id == self_id:
            raise HelpCategoryInvalidError("上级分类不能是自身")
        rows = await self._repo.list_categories()
        by_id: ConcurrentStableDict[int, SysHelpCategory] = ConcurrentStableDict((int(row.id), row) for row in rows)
        depth = 1
        current = by_id.get(parent_id)
        while current is not None:
            if self_id is not None and int(current.id) == self_id:
                raise HelpCategoryInvalidError("上级分类不能是自身的子孙")
            depth += 1
            if depth > MAX_CATEGORY_DEPTH:
                raise HelpCategoryInvalidError(f"分类深度超出上限（{MAX_CATEGORY_DEPTH} 级）")
            parent_of_current = int(current.parent_id)
            current = by_id.get(parent_of_current) if parent_of_current != 0 else None

    async def _assert_category_name_free(self, parent_id: int, name: str, *, exclude_id: int | None = None) -> None:
        """校验同级分类名唯一。

        Args:
            parent_id: 上级分类 ID。
            name: 分类名。
            exclude_id: 排除的分类主键（编辑自身时传）。

        Raises:
            HelpCategoryInvalidError: 同级同名（`40023`）。
        """
        existing = await self._repo.find_category(parent_id=parent_id, name=name, exclude_id=exclude_id)
        if existing is not None:
            raise HelpCategoryInvalidError(f"同级分类名已存在：{name}")

    # ------------------------------------------------------------------ 文章

    async def list_articles(self, filters: HelpArticleFilters, *, page: int, size: int) -> HelpManageArticlePage:
        """管理面文章列表。

        Args:
            filters: 筛选条件。
            page: 页码。
            size: 每页条数。

        Returns:
            HelpManageArticlePage: 分页结果。
        """
        rows, total = await self._repo.list_articles(filters, offset=(page - 1) * size, limit=size)
        paths = await self._category_paths()
        items = ConcurrentStableList(self._item(row, paths) for row in rows)
        return HelpManageArticlePage(list=items, total=total, page=page, size=size)

    async def get_article(self, article_id: int) -> HelpManageArticleDetail:
        """管理面文章详情。

        Args:
            article_id: 文章主键。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
        """
        row = await self._article_or_raise(article_id)
        return await self._detail(row)

    async def create_article(self, payload: HelpManageArticleCreate, *, locale: str) -> HelpManageArticleDetail:
        """新建文章（默认草稿）。

        Args:
            payload: 新建请求。
            locale: 请求语言（补默认语言行时兜底）。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleContentInvalidError: 内容非法 / AI 未审核（`40018`）。
            HelpLocaleUnsupportedError: 语言不受支持（`40022`）。
            HelpAnchorUnresolvedError: 锚点不可解析（`40008`）。
            HelpArticleTargetConflictError: 目标重复或占用（`40019`）。
            HelpCategoryNotFoundError: 分类不存在（`40014`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            self._assert_article_status(payload.status)
            await self._category_or_raise(int(payload.category_id))
            default_locale = await load_help_default_locale(self._session)
            locales = await load_help_locales(self._session)
            texts, title, content = await self._resolve_texts(
                title=payload.title,
                content=payload.content,
                i18n=payload.i18n,
                default_locale=default_locale,
                allowed_locales=locales,
                locale=locale,
            )
            self._assert_ai_provenance(payload.generated_by, payload.ai_model, payload.reviewed_by)
            if payload.status == ARTICLE_STATUS_PUBLISHED:
                self._assert_publish_ready(payload.generated_by, payload.reviewed_by, content)
            targets = await self._validate_targets(payload.targets)
            if payload.status == ARTICLE_STATUS_PUBLISHED:
                await self._assert_targets_free(targets, exclude_article_id=0)
            row = await self._repo.create_article(
                category_id=int(payload.category_id),
                title=title,
                content=content,
                status=payload.status,
                is_top=payload.is_top,
                author_id=get_current_user_id(),
                generated_by=payload.generated_by,
                ai_model=payload.ai_model,
                reviewed_by=payload.reviewed_by,
                publish_now=payload.status == ARTICLE_STATUS_PUBLISHED,
            )
            await self._repo.content.replace_i18n(int(row.id), ConcurrentStableFrozenDict(texts))
            await self._repo.content.replace_targets(int(row.id), targets)
            if payload.status == ARTICLE_STATUS_PUBLISHED:
                await self._publish(ARTICLE_PUBLISHED_EVENT, row, targets)
            await self._bump_cache()
            return await self._detail(row)

    async def update_article(
        self, article_id: int, payload: HelpManageArticleUpdate, *, locale: str
    ) -> HelpManageArticleDetail:
        """编辑文章（显式状态，缺省沿用；包来源自动本地覆盖）。

        Args:
            article_id: 文章主键。
            payload: 编辑请求。
            locale: 请求语言。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
            HelpArticleStateInvalidError: 状态迁移不允许（`40017`）。
            HelpArticleContentInvalidError: 内容非法 / AI 未审核（`40018`）。
            HelpLocaleUnsupportedError: 语言不受支持（`40022`）。
            HelpAnchorUnresolvedError: 锚点不可解析（`40008`）。
            HelpArticleTargetConflictError: 目标重复或占用（`40019`）。
            HelpCategoryNotFoundError: 分类不存在（`40014`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._article_or_raise(article_id)
            old_status = str(row.status)
            new_status = payload.status or old_status
            self._assert_article_status(new_status)
            if payload.status is not None and new_status != old_status:
                self._assert_transition(old_status, new_status)
            if payload.category_id is not None:
                await self._category_or_raise(int(payload.category_id))
                row.category_id = int(payload.category_id)
            default_locale = await load_help_default_locale(self._session)
            locales = await load_help_locales(self._session)
            existing = await self._repo.content.load_article_i18n(ConcurrentStableList((article_id,)))
            texts, title, content = await self._resolve_texts(
                title=payload.title if payload.title is not None else str(row.title),
                content=payload.content if payload.content is not None else str(row.content),
                i18n=payload.i18n,
                default_locale=default_locale,
                allowed_locales=locales,
                locale=locale,
                existing=existing.get(article_id),
                replace_default=payload.i18n is None and (payload.title is not None or payload.content is not None),
            )
            generated_by = payload.generated_by or str(row.generated_by)
            ai_model = payload.ai_model if payload.ai_model is not None else row.ai_model
            reviewed_by = payload.reviewed_by if payload.reviewed_by is not None else row.reviewed_by
            self._assert_ai_provenance(generated_by, ai_model, reviewed_by)
            if new_status == ARTICLE_STATUS_PUBLISHED:
                self._assert_publish_ready(generated_by, reviewed_by, content)
            row.title = title
            row.content = content
            row.status = new_status
            if payload.is_top is not None:
                row.is_top = payload.is_top
            row.generated_by = generated_by
            row.ai_model = ai_model if generated_by == GENERATED_BY_AI else None
            row.reviewed_by = reviewed_by
            if new_status == ARTICLE_STATUS_PUBLISHED and row.publish_at is None:
                row.publish_at = _utc_now()
            targets: ConcurrentStableFrozenList[tuple[str, str]] | None = None
            if payload.targets is not None:
                targets = await self._validate_targets(payload.targets)
                if new_status == ARTICLE_STATUS_PUBLISHED:
                    await self._assert_targets_free(targets, exclude_article_id=article_id)
                await self._repo.content.replace_targets(article_id, targets)
            await self._repo.content.replace_i18n(article_id, ConcurrentStableFrozenDict(texts))
            if str(row.source) != ARTICLE_SOURCE_TENANT:
                row.local_override = True
            await self._repo.save_article(row)
            published_targets = targets
            if published_targets is None:
                loaded = await self._repo.content.load_article_targets(ConcurrentStableList((article_id,)))
                published_targets = loaded.get(article_id) or ConcurrentStableFrozenList[tuple[str, str]]()
            await self._publish_for_update(row, old_status, published_targets, changed=bool(payload.model_fields_set))
            await self._bump_cache()
            return await self._detail(row)

    async def delete_article(self, article_id: int) -> HelpManageArticleDeleteResult:
        """软删除文章（包来源拒绝）。

        Args:
            article_id: 文章主键。

        Returns:
            HelpManageArticleDeleteResult: 删除结果。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
            HelpArticleStateInvalidError: 包来源文章不可删除（`40017`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._article_or_raise(article_id)
            if str(row.source) != ARTICLE_SOURCE_TENANT:
                raise HelpArticleStateInvalidError("产品包来源文章不可删除，请使用「下架」")
            targets = (await self._repo.content.load_article_targets(ConcurrentStableList((article_id,)))).get(
                article_id
            ) or ConcurrentStableFrozenList[tuple[str, str]]()
            if str(row.status) == ARTICLE_STATUS_PUBLISHED:
                await self._publish(ARTICLE_DELETED_EVENT, row, targets)
            await self._repo.soft_delete_article(row)
            await self._bump_cache()
            return HelpManageArticleDeleteResult(applied=True)

    async def publish_article(self, article_id: int) -> HelpManageArticleDetail:
        """发布文章（草稿 / 下架 → 已发布）。

        Args:
            article_id: 文章主键。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
            HelpArticleStateInvalidError: 状态迁移不允许（`40017`）。
            HelpArticleContentInvalidError: AI 未审核 / 内容为空（`40018`）。
        """
        return await self._transition(article_id, target=ARTICLE_STATUS_PUBLISHED)

    async def offline_article(self, article_id: int) -> HelpManageArticleDetail:
        """下架文章（已发布 → 已下架）。

        Args:
            article_id: 文章主键。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
            HelpArticleStateInvalidError: 状态迁移不允许（`40017`）。
        """
        return await self._transition(article_id, target=ARTICLE_STATUS_OFFLINE)

    async def _transition(self, article_id: int, *, target: str) -> HelpManageArticleDetail:
        """执行状态迁移（发布 / 下架共用）。

        Args:
            article_id: 文章主键。
            target: 目标状态。

        Returns:
            HelpManageArticleDetail: 详情。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
            HelpArticleStateInvalidError: 状态迁移不允许（`40017`）。
            HelpArticleContentInvalidError: AI 未审核 / 内容为空（`40018`）。
        """
        await self._uow.rollback()
        async with self._uow.begin():
            row = await self._article_or_raise(article_id)
            old_status = str(row.status)
            self._assert_transition(old_status, target)
            if target == ARTICLE_STATUS_PUBLISHED:
                self._assert_publish_ready(str(row.generated_by), row.reviewed_by, str(row.content))
            row.status = target
            if target == ARTICLE_STATUS_PUBLISHED and row.publish_at is None:
                row.publish_at = _utc_now()
            await self._repo.save_article(row)
            targets = (await self._repo.content.load_article_targets(ConcurrentStableList((article_id,)))).get(
                article_id
            ) or ConcurrentStableFrozenList[tuple[str, str]]()
            if target == ARTICLE_STATUS_PUBLISHED:
                await self._publish(ARTICLE_PUBLISHED_EVENT, row, targets)
            else:
                await self._publish(ARTICLE_UPDATED_EVENT, row, targets)
            await self._bump_cache()
            return await self._detail(row)

    async def _article_or_raise(self, article_id: int) -> SysHelpArticle:
        """取文章或抛 40016。

        Args:
            article_id: 文章主键。

        Returns:
            SysHelpArticle: 文章行。

        Raises:
            HelpArticleNotFoundError: 文章不存在（`40016`）。
        """
        row = await self._repo.get_article(article_id)
        if row is None:
            raise HelpArticleNotFoundError(f"文章不存在：{article_id}")
        return row

    def _assert_article_status(self, status: str) -> None:
        """校验文章状态值域。

        Args:
            status: 状态。

        Raises:
            ParamError: 状态非法（`10001`）。
        """
        if status not in ARTICLE_STATUSES:
            raise ParamError(f"文章状态非法：{status}")

    def _assert_transition(self, old: str, new: str) -> None:
        """校验状态迁移合法性。

        Args:
            old: 当前状态。
            new: 目标状态。

        Raises:
            HelpArticleStateInvalidError: 迁移不允许（`40017`）。
        """
        if old == new:
            raise HelpArticleStateInvalidError(f"文章已处于目标状态：{new}")
        if new == ARTICLE_STATUS_PUBLISHED and old in (ARTICLE_STATUS_DRAFT, ARTICLE_STATUS_OFFLINE):
            return
        if new == ARTICLE_STATUS_OFFLINE and old == ARTICLE_STATUS_PUBLISHED:
            return
        raise HelpArticleStateInvalidError(f"文章状态不允许从 {old} 变为 {new}")

    def _assert_publish_ready(self, generated_by: str, reviewed_by: str | None, content: str) -> None:
        """校验发布前置（AI 审核人 + 正文非空）。

        Args:
            generated_by: 生成方式。
            reviewed_by: 审核人。
            content: 默认语言正文。

        Raises:
            HelpArticleContentInvalidError: 未审核或正文为空（`40018`）。
        """
        if generated_by == GENERATED_BY_AI and not (reviewed_by or "").strip():
            raise HelpArticleContentInvalidError("AI 生成的文章未填写审核人，不允许发布")
        if html_text_length(content) == 0:
            raise HelpArticleContentInvalidError("文章正文清洗后为空")

    def _assert_ai_provenance(self, generated_by: str, ai_model: str | None, reviewed_by: str | None) -> None:
        """校验来源留痕自洽（manual 不得带模型；AI 必带模型）。

        Args:
            generated_by: 生成方式。
            ai_model: AI 模型。
            reviewed_by: 审核人。

        Raises:
            ParamError: 生成方式非法（`10001`）。
            HelpArticleContentInvalidError: 来源留痕不自洽（`40018`）。
        """
        del reviewed_by
        if generated_by not in GENERATED_BY_VALUES:
            raise ParamError(f"生成方式非法：{generated_by}")
        if generated_by == GENERATED_BY_MANUAL and ai_model:
            raise HelpArticleContentInvalidError("人工撰写的文章不应填写 AI 模型")
        if generated_by == GENERATED_BY_AI and not (ai_model or "").strip():
            raise HelpArticleContentInvalidError("AI 生成的文章必须填写模型")

    async def _resolve_texts(
        self,
        *,
        title: str,
        content: str,
        i18n: ConcurrentStableDict[str, HelpManageLocaleText] | None,
        default_locale: str,
        allowed_locales: ConcurrentStableFrozenList[str],
        locale: str,
        existing: ConcurrentStableFrozenDict[str, tuple[str, str]] | None = None,
        replace_default: bool = False,
    ) -> tuple[ConcurrentStableDict[str, tuple[str, str]], str, str]:
        """整理并清洗多语言文案（默认语言必填；主表快照取默认语言）。

        Args:
            title: 请求体默认语言标题（缺多语言行 / 覆盖默认语言时用）。
            content: 请求体默认语言正文。
            i18n: 请求体多语言映射（None 表示沿用 `existing`）。
            default_locale: 租户默认语言。
            allowed_locales: 租户启用语言清单。
            locale: 请求语言（仅作兜底提示）。
            existing: 既有文案（编辑时未传 i18n 用）。
            replace_default: 是否用 `title` / `content` 覆盖默认语言行。

        Returns:
            tuple[ConcurrentStableDict[str, tuple[str, str]], str, str]: 语言文案 / 主表标题 / 主表正文。

        Raises:
            HelpLocaleUnsupportedError: 语言不在启用清单（`40022`）。
            HelpArticleContentInvalidError: 正文清洗后为空 / 超限（`40018`）。
        """
        raw: ConcurrentStableDict[str, HelpManageLocaleText] = (
            ConcurrentStableDict(i18n) if i18n else ConcurrentStableDict()
        )
        if not raw and existing:
            for code, (item_title, item_content) in existing.items():
                raw.set(code, HelpManageLocaleText(title=item_title, content=item_content))
        texts: ConcurrentStableDict[str, tuple[str, str]] = ConcurrentStableDict()
        if raw:
            for raw_locale, text in raw.items():
                code = normalize_locale(raw_locale)
                if code not in allowed_locales:
                    raise HelpLocaleUnsupportedError(f"语言不在启用清单内：{raw_locale}")
                texts.set(code, self._clean_text(text.title, text.content, where=code))
        if default_locale not in texts or replace_default:
            texts.set(default_locale, self._clean_text(title, content, where=default_locale))
        main_title, main_content = texts.get(default_locale) or ("", "")
        del locale
        return texts, main_title, main_content

    def _clean_text(self, title: str, content: str, *, where: str) -> tuple[str, str]:
        """清洗单语言文案并校验长度 / 空内容。

        Args:
            title: 标题。
            content: 正文 HTML。
            where: 语言标识（错误提示用）。

        Returns:
            tuple[str, str]: （标题, 清洗后正文）。

        Raises:
            HelpArticleContentInvalidError: 标题为空 / 超长、正文清洗后为空 / 超限（`40018`）。
        """
        clean_title = (title or "").strip()
        clean_content = sanitize_html(content or "").strip()
        if html_text_length(clean_content) == 0:
            raise HelpArticleContentInvalidError(f"正文清洗后为空（{where}）")
        if len(clean_content.encode("utf-8")) > MAX_ARTICLE_CONTENT_BYTES:
            raise HelpArticleContentInvalidError(f"正文超出 {MAX_ARTICLE_CONTENT_BYTES} 字节（{where}）")
        return clean_title, clean_content

    async def _validate_targets(
        self, items: ConcurrentStableList[HelpManageTargetItem]
    ) -> ConcurrentStableFrozenList[tuple[str, str]]:
        """校验并归一文章目标（形态 + 存在性 + 类型匹配 + 去重）。

        Args:
            items: 请求目标清单。

        Returns:
            ConcurrentStableFrozenList[tuple[str, str]]: 归一后的（类型, 键）。

        Raises:
            HelpArticleContentInvalidError: 类型未知 / 键缺失或形态不符（`40018`）。
            HelpAnchorUnresolvedError: 锚点不存在或类型不匹配（`40008`）。
            HelpArticleTargetConflictError: 同文章目标重复（`40019`）。
        """
        if not items:
            return ConcurrentStableFrozenList()
        anchors: ConcurrentStableFrozenDict[str, HelpAnchorKind] = await load_help_anchor_kinds(self._platform_session)
        normalized: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()
        for item in items:
            target_type = item.type.strip()
            if not is_known_target_type(target_type):
                raise HelpArticleContentInvalidError(f"目标类型非法：{target_type}")
            key = "" if target_type == TARGET_TYPE_GLOBAL else item.key.strip()
            if target_type != TARGET_TYPE_GLOBAL:
                if not key:
                    raise HelpArticleContentInvalidError(f"目标键不能为空：{target_type}")
                if not target_key_matches(target_type, key):
                    raise HelpArticleContentInvalidError(f"目标键与类型不匹配：{target_type}:{key}")
            pair = (target_type, key)
            if pair in normalized:
                raise HelpArticleTargetConflictError(f"同文章目标重复：{target_type}:{key}")
            problem = target_problem(target_type, key, anchors)
            if problem is not None:
                raise HelpAnchorUnresolvedError(f"帮助锚点不可解析：{problem}")
            normalized.add(pair)
        return ConcurrentStableFrozenList(normalized)

    async def _assert_targets_free(
        self,
        targets: ConcurrentStableFrozenList[tuple[str, str]],
        *,
        exclude_article_id: int,
    ) -> None:
        """校验目标未被其它已发布租户自建文章占用。

        Args:
            targets: 目标清单。
            exclude_article_id: 排除的文章主键（新建传 0）。

        Raises:
            HelpArticleTargetConflictError: 目标已被占用（`40019`）。
        """
        for target_type, target_key in targets:
            if target_type == TARGET_TYPE_GLOBAL:
                continue
            occupied = await self._repo.count_published_tenant_on_target(
                target_type=target_type,
                target_key=target_key,
                exclude_article_id=exclude_article_id,
            )
            if occupied:
                raise HelpArticleTargetConflictError(f"目标已被其它已发布文章占用：{target_type}:{target_key}")

    async def _publish_for_update(
        self,
        row: SysHelpArticle,
        old_status: str,
        targets: ConcurrentStableFrozenList[tuple[str, str]],
        *,
        changed: bool,
    ) -> None:
        """按编辑结果发布事件（草稿变更不发）。

        Args:
            row: 文章行。
            old_status: 编辑前状态。
            targets: 目标清单。
            changed: 请求是否带任何字段。
        """
        new_status = str(row.status)
        if new_status == ARTICLE_STATUS_PUBLISHED and old_status != ARTICLE_STATUS_PUBLISHED:
            await self._publish(ARTICLE_PUBLISHED_EVENT, row, targets)
            return
        if old_status == ARTICLE_STATUS_PUBLISHED and new_status != ARTICLE_STATUS_PUBLISHED:
            await self._publish(ARTICLE_UPDATED_EVENT, row, targets)
            return
        if new_status == ARTICLE_STATUS_PUBLISHED and changed:
            await self._publish(ARTICLE_UPDATED_EVENT, row, targets)

    async def _publish(
        self,
        event_type: str,
        row: SysHelpArticle,
        targets: ConcurrentStableFrozenList[tuple[str, str]],
    ) -> None:
        """在同一事务内发布帮助文章事件。

        Args:
            event_type: 事件类型。
            row: 文章行。
            targets: 目标清单（取首个非 global 键作为载荷）。
        """
        target_key = ""
        for target_type, key in targets:
            if target_type != TARGET_TYPE_GLOBAL:
                target_key = key
                break
        await self._outbox.enqueue(
            self._session,
            EventEnvelope(
                event_type=event_type,
                payload=ConcurrentStableDict(
                    {
                        "article_id": str(int(row.id)),
                        "category_id": str(int(row.category_id)),
                        "target_key": target_key,
                    }
                ),
                aggregate_key=f"help:{int(row.id)}",
            ),
        )

    async def _bump_cache(self) -> None:
        """递增内容版本键（解析缓存即时失效）。"""
        await bump_content_version(self._cache, tenant=self._tenant)

    async def _category_paths(self) -> ConcurrentStableDict[int, str]:
        """取分类主键 → 路径映射。

        Returns:
            ConcurrentStableDict[int, str]: 分类路径。
        """
        rows = await self._repo.list_categories()
        paths: ConcurrentStableDict[int, str] = self._repo.content.build_path_map(rows)
        return paths

    def _item(self, row: SysHelpArticle, paths: ConcurrentStableDict[int, str]) -> HelpManageArticleItem:
        """文章行 → 管理面列表行。

        Args:
            row: 文章行。
            paths: 分类路径映射。

        Returns:
            HelpManageArticleItem: 列表行。
        """
        return HelpManageArticleItem(
            id=int(row.id),
            title=str(row.title),
            category_id=int(row.category_id),
            category_path=paths.get(int(row.category_id), ""),
            status=str(row.status),
            is_top=bool(row.is_top),
            source=str(row.source),
            local_override=bool(row.local_override),
            generated_by=str(row.generated_by),
            reviewed_by=row.reviewed_by,
            publish_at=row.publish_at,
            view_count=int(row.view_count),
            helpful_count=int(row.helpful_count),
            unhelpful_count=int(row.unhelpful_count),
            updated_at=row.updated_at,
        )

    async def _detail(self, row: SysHelpArticle) -> HelpManageArticleDetail:
        """文章行 → 管理面详情（含正文、全语言与目标）。

        Args:
            row: 文章行。

        Returns:
            HelpManageArticleDetail: 详情。
        """
        article_id = int(row.id)
        paths = await self._category_paths()
        i18n = await self._repo.content.load_article_i18n(ConcurrentStableList((article_id,)))
        targets = await self._repo.content.load_article_targets(ConcurrentStableList((article_id,)))
        item = self._item(row, paths)
        return HelpManageArticleDetail(
            **item.model_dump(),
            content=str(row.content),
            i18n=ConcurrentStableDict(
                (code, HelpManageLocaleText(title=title, content=content))
                for code, (title, content) in (
                    i18n.get(article_id) or ConcurrentStableFrozenDict[str, tuple[str, str]]()
                ).items()
            ),
            targets=ConcurrentStableList(
                HelpManageTargetItem(type=target_type, key=target_key)
                for target_type, target_key in (
                    targets.get(article_id) or ConcurrentStableFrozenList[tuple[str, str]]()
                )
            ),
            package_id=int(row.package_id) if row.package_id is not None else None,
            source_key=row.source_key,
            ai_model=row.ai_model,
            author_id=int(row.author_id) if row.author_id is not None else None,
            created_at=row.created_at,
            version=int(row.version),
        )


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，落 DATETIME）。

    Returns:
        datetime: UTC 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)
