"""帮助内容数据访问：分类 / 文章 / 多语言 / 锚点 / 包登记（08_03）。

只承载 SQL 与行操作，不含装载策略（计划器在 `services/package.py`）。解析读面也复用本仓储，
保证「装载写的形状」与「解析读的形状」同源。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import HelpPackageNotLoadedError
from bms_core.core.objects import BaseFrameworkObject, BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.content import (
    HelpArticle,
    HelpArticleSummary,
    HelpCategory,
    HelpContentQuery,
    HelpContentResult,
    HelpLevel,
)
from bms_core.help.values import (
    ARTICLE_STATUS_PUBLISHED,
    SOURCE_PRIORITY,
    TARGET_TYPE_ACTION,
    TARGET_TYPE_FIELD,
    TARGET_TYPE_FORM,
    TARGET_TYPE_GLOBAL,
    TARGET_TYPE_MODULE,
)
from bms_core.i18n.rules import normalize_locale
from bms_core.models.platform.help import (
    SysHelpArticle,
    SysHelpArticleI18n,
    SysHelpArticleTarget,
    SysHelpCategory,
    SysHelpPackage,
)
from bms_core.repositories.help_locale import load_help_default_locale
from bms_core.repositories.i18n import load_i18n_all_texts, load_i18n_texts, replace_i18n_texts

__all__ = [
    "HelpArticleRecord",
    "HelpContentRepository",
    "HelpTargetOccupancy",
]

_ARTICLE_TEXT_COLUMNS: ConcurrentStableList[str] = ConcurrentStableList(("title", "content"))
"""文章附表文案列。"""

_MAX_MISS_CATEGORIES = 50
"""未命中时返回的顶层分类上限。"""

_LEVEL_TARGET_TYPES: ConcurrentStableFrozenDict[HelpLevel, str] = ConcurrentStableFrozenDict(
    {
        HelpLevel.FIELD: TARGET_TYPE_FIELD,
        HelpLevel.ACTION: TARGET_TYPE_ACTION,
        HelpLevel.FORM: TARGET_TYPE_FORM,
        HelpLevel.MODULE: TARGET_TYPE_MODULE,
        HelpLevel.GLOBAL: TARGET_TYPE_GLOBAL,
    }
)
"""解析层级 → 目标类型。"""


@dataclass(frozen=True)
class HelpArticleRecord(BaseValueObject):
    """包来源文章行 + 其版本信息（升级比对用）。

    Attributes:
        article: 文章行。
        package_version: 来源包版本（自建文章为空串）。
        product_key: 来源产品键（自建文章为空串）。
    """

    article: SysHelpArticle
    package_version: str
    product_key: str


@dataclass(frozen=True)
class HelpTargetOccupancy(BaseValueObject):
    """一个目标当前被哪篇文章占用（冲突检测用）。

    Attributes:
        article_id: 文章主键。
        source: 文章来源。
        source_key: 包内稳定键（自建为空串）。
        product_key: 来源产品键（自建为空串）。
        package_version: 来源包版本（自建为空串）。
    """

    article_id: int
    source: str
    source_key: str
    product_key: str
    package_version: str


class HelpContentRepository(BaseFrameworkObject):
    """帮助内容仓储（租户库会话）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._session = session

    # ---- 分类 ----

    async def load_categories(self) -> ConcurrentStableList[SysHelpCategory]:
        """取全部未软删分类（主键升序）。

        Returns:
            ConcurrentStableList[SysHelpCategory]: 分类行。
        """
        statement = select(SysHelpCategory).where(SysHelpCategory.deleted_at.is_(None)).order_by(SysHelpCategory.id)
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    @staticmethod
    def build_path_map(categories: ConcurrentStableList[SysHelpCategory]) -> ConcurrentStableDict[int, str]:
        """按 `parent_id` 递归拼出「分类主键 → 路径」。

        Args:
            categories: 分类行。

        Returns:
            ConcurrentStableDict[int, str]: 分类主键 → 路径（父级缺失 / 断链的分支跳过）。
        """
        by_id: ConcurrentStableDict[int, SysHelpCategory] = ConcurrentStableDict(
            (int(row.id), row) for row in categories
        )
        resolved: ConcurrentStableDict[int, str] = ConcurrentStableDict()
        for category in categories:
            path = HelpContentRepository._path_of(category, by_id, resolved)
            if path is not None:
                resolved.set(int(category.id), path)
        return resolved

    @staticmethod
    def _path_of(
        category: SysHelpCategory,
        by_id: ConcurrentStableDict[int, SysHelpCategory],
        resolved: ConcurrentStableDict[int, str],
    ) -> str | None:
        """取单个分类路径（带记忆；断链返回 None）。

        Args:
            category: 分类行。
            by_id: 主键 → 分类行。
            resolved: 已解析路径缓存。

        Returns:
            str | None: 路径；父级缺失或成环返回 None。
        """
        known = resolved.get(int(category.id))
        if known is not None:
            return known
        parts: ConcurrentStableList[str] = ConcurrentStableList()
        current: SysHelpCategory | None = category
        seen: ConcurrentStableList[int] = ConcurrentStableList()
        while current is not None:
            current_id = int(current.id)
            if current_id in seen:
                return None
            seen.add(current_id)
            parts.add(current.name)
            parent_id = int(current.parent_id)
            if parent_id == 0:
                break
            current = by_id.get(parent_id)
        ordered = ConcurrentStableFrozenList(reversed(parts))
        path = "/".join(ordered)
        resolved.set(int(category.id), path)
        return path

    async def create_category(self, *, name: str, parent_id: int, sort: int) -> SysHelpCategory:
        """新建分类（调用方负责 flush）。

        Args:
            name: 分类名。
            parent_id: 上级分类 ID（0 = 根）。
            sort: 同级排序。

        Returns:
            SysHelpCategory: 新行。
        """
        row = SysHelpCategory(parent_id=parent_id, name=name, sort=sort, status="enabled")
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_category_sort(self, row: SysHelpCategory, sort: int) -> None:
        """更新分类排序。

        Args:
            row: 分类行。
            sort: 新排序。
        """
        row.sort = sort
        await self._session.flush()

    # ---- 包登记 ----

    async def load_packages(self, product_key: str) -> ConcurrentStableList[SysHelpPackage]:
        """取某产品全部包登记行（主键升序）。

        Args:
            product_key: 产品键。

        Returns:
            ConcurrentStableList[SysHelpPackage]: 包行。
        """
        statement = (
            select(SysHelpPackage)
            .where(SysHelpPackage.product_key == product_key, SysHelpPackage.deleted_at.is_(None))
            .order_by(SysHelpPackage.id)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def get_package(self, package_id: int) -> SysHelpPackage:
        """按主键取包登记行（未软删）。

        Args:
            package_id: 包行主键。

        Returns:
            SysHelpPackage: 包行。

        Raises:
            HelpPackageNotLoadedError: 行不存在（40012）。
        """
        statement = select(SysHelpPackage).where(
            SysHelpPackage.id == package_id,
            SysHelpPackage.deleted_at.is_(None),
        )
        row = (await self._session.execute(statement)).scalars().first()
        if row is None:
            raise HelpPackageNotLoadedError(f"帮助包登记不存在：{package_id}")
        return row

    async def create_package(
        self,
        *,
        product_key: str,
        package_version: str,
        schema_version: int,
        checksum: str,
        article_count: int,
        generated_at: datetime | None,
    ) -> SysHelpPackage:
        """新建包登记行（调用方负责 flush / 事务）。

        Args:
            product_key: 产品键。
            package_version: 版本。
            schema_version: 包格式版本。
            checksum: 校验和。
            article_count: 清单文章总数。
            generated_at: 清单生成时间。

        Returns:
            SysHelpPackage: 新行。
        """
        row = SysHelpPackage(
            product_key=product_key,
            package_version=package_version,
            schema_version=schema_version,
            checksum=checksum,
            article_count=article_count,
            generated_at=generated_at,
            loaded_at=_utc_now(),
            status="loaded",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_package_loaded(
        self,
        row: SysHelpPackage,
        *,
        checksum: str,
        article_count: int,
        generated_at: datetime | None,
    ) -> None:
        """把已存在（被卸载 / 过期）的同版本行恢复为当前版本。

        Args:
            row: 包行。
            checksum: 校验和。
            article_count: 清单文章总数。
            generated_at: 清单生成时间。
        """
        row.checksum = checksum
        row.article_count = article_count
        row.generated_at = generated_at
        row.loaded_at = _utc_now()
        row.status = "loaded"
        await self._session.flush()

    async def outdate_other_packages(self, product_key: str, keep_id: int) -> None:
        """把同产品其他 `loaded` 行置 `outdated`。

        Args:
            product_key: 产品键。
            keep_id: 当前版本行主键。
        """
        rows = await self.load_packages(product_key)
        for row in rows:
            if int(row.id) != keep_id and row.status == "loaded":
                row.status = "outdated"
        await self._session.flush()

    async def unload_packages(self, product_key: str) -> ConcurrentStableList[SysHelpPackage]:
        """把某产品全部包行置 `unloaded`，返回受影响行。

        Args:
            product_key: 产品键。

        Returns:
            ConcurrentStableList[SysHelpPackage]: 包行（原状态）。
        """
        rows = await self.load_packages(product_key)
        for row in rows:
            row.status = "unloaded"
        await self._session.flush()
        return rows

    async def load_package_articles(self, product_key: str) -> ConcurrentStableList[HelpArticleRecord]:
        """取某产品包来源文章（含空来源键的自建文章排除在外）。

        Args:
            product_key: 产品键。

        Returns:
            ConcurrentStableList[HelpArticleRecord]: 文章行 + 版本信息。
        """
        statement = (
            select(SysHelpArticle, SysHelpPackage)
            .join(SysHelpPackage, SysHelpPackage.id == SysHelpArticle.package_id)
            .where(
                SysHelpPackage.product_key == product_key,
                SysHelpArticle.deleted_at.is_(None),
                SysHelpPackage.deleted_at.is_(None),
            )
            .order_by(SysHelpArticle.id)
        )
        rows = (await self._session.execute(statement)).all()
        return ConcurrentStableList(
            HelpArticleRecord(
                article=article,
                package_version=str(package.package_version),
                product_key=str(package.product_key),
            )
            for article, package in rows
        )

    async def get_article(self, article_id: int) -> SysHelpArticle:
        """按主键取未软删文章。

        Args:
            article_id: 文章主键。

        Returns:
            SysHelpArticle: 文章行。

        Raises:
            HelpPackageNotLoadedError: 行不存在（40012）。
        """
        statement = select(SysHelpArticle).where(
            SysHelpArticle.id == article_id,
            SysHelpArticle.deleted_at.is_(None),
        )
        row = (await self._session.execute(statement)).scalars().first()
        if row is None:
            raise HelpPackageNotLoadedError(f"帮助文章不存在：{article_id}")
        return row

    # ---- 文章 ----

    async def load_article_targets(
        self, article_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableFrozenList[tuple[str, str]]]:
        """取文章目标集合。

        Args:
            article_ids: 文章主键。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableFrozenList[tuple[str, str]]]: 文章 → [(类型, 键)]。
        """
        if not article_ids:
            return ConcurrentStableDict()
        statement = select(SysHelpArticleTarget).where(
            SysHelpArticleTarget.article_id.in_(list(article_ids)),
            SysHelpArticleTarget.deleted_at.is_(None),
        )
        rows = (await self._session.execute(statement)).scalars().all()
        grouped: ConcurrentStableDict[int, ConcurrentStableList[tuple[str, str]]] = ConcurrentStableDict()
        for row in rows:
            bucket = grouped.get(int(row.article_id))
            if bucket is None:
                bucket = ConcurrentStableList[tuple[str, str]]()
                grouped.set(int(row.article_id), bucket)
            bucket.add((str(row.target_type), str(row.target_key)))
        return ConcurrentStableDict(
            (article_id, ConcurrentStableFrozenList(sorted(bucket))) for article_id, bucket in grouped.items()
        )

    async def load_article_i18n(
        self, article_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableDict[int, ConcurrentStableFrozenDict[str, tuple[str, str]]]:
        """取文章全部语言文案（维护 / 比对用，不做回退）。

        Args:
            article_ids: 文章主键。

        Returns:
            ConcurrentStableDict[int, ConcurrentStableFrozenDict[str, tuple[str, str]]]:
                文章 → 语言 → (标题, 正文)。
        """
        if not article_ids:
            return ConcurrentStableDict()
        texts = await load_i18n_all_texts(
            self._session,
            SysHelpArticleI18n,
            "article_id",
            article_ids,
            text_columns=_ARTICLE_TEXT_COLUMNS,
        )
        result: ConcurrentStableDict[int, ConcurrentStableFrozenDict[str, tuple[str, str]]] = ConcurrentStableDict()
        for article_id, by_locale in texts.items():
            rows: ConcurrentStableList[tuple[str, tuple[str, str]]] = ConcurrentStableList()
            for locale, values in by_locale.items():
                rows.add(
                    (
                        normalize_locale(locale),
                        (values.get("title") or "", values.get("content") or ""),
                    )
                )
            result.set(article_id, ConcurrentStableFrozenDict(rows))
        return result

    async def load_target_occupancy(
        self, pairs: ConcurrentStableList[tuple[str, str]]
    ) -> ConcurrentStableDict[tuple[str, str], ConcurrentStableList[HelpTargetOccupancy]]:
        """查目标当前被哪些已发布文章占用。

        Args:
            pairs: [(目标类型, 目标键)]（去重前）。

        Returns:
            ConcurrentStableDict[tuple[str, str], ConcurrentStableList[HelpTargetOccupancy]]:
                (类型, 键) → 占用清单。
        """
        keys = ConcurrentStableList({key for _, key in pairs})
        if not keys:
            return ConcurrentStableDict()
        statement = (
            select(SysHelpArticle, SysHelpArticleTarget, SysHelpPackage)
            .join(SysHelpArticleTarget, SysHelpArticleTarget.article_id == SysHelpArticle.id)
            .outerjoin(SysHelpPackage, SysHelpPackage.id == SysHelpArticle.package_id)
            .where(
                SysHelpArticleTarget.target_key.in_(list(keys)),
                SysHelpArticleTarget.deleted_at.is_(None),
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
            )
            .order_by(SysHelpArticle.id)
        )
        rows = (await self._session.execute(statement)).all()
        wanted = set(pairs)
        grouped: ConcurrentStableDict[tuple[str, str], ConcurrentStableList[HelpTargetOccupancy]] = (
            ConcurrentStableDict()
        )
        for article, target, package in rows:
            pair = (str(target.target_type), str(target.target_key))
            if pair not in wanted:
                continue
            bucket = grouped.get(pair)
            if bucket is None:
                bucket = ConcurrentStableList[HelpTargetOccupancy]()
                grouped.set(pair, bucket)
            bucket.add(
                HelpTargetOccupancy(
                    article_id=int(article.id),
                    source=str(article.source),
                    source_key=str(article.source_key or ""),
                    product_key=str(package.product_key) if package is not None else "",
                    package_version=str(package.package_version) if package is not None else "",
                )
            )
        return grouped

    async def create_article(
        self,
        *,
        category_id: int,
        title: str,
        content: str,
        status: str,
        is_top: bool,
        source: str,
        package_id: int,
        source_key: str,
        generated_by: str,
        ai_model: str | None,
        reviewed_by: str | None,
    ) -> SysHelpArticle:
        """新建包来源文章（调用方负责 flush）。

        Args:
            category_id: 分类主键。
            title: 默认语言标题。
            content: 默认语言正文。
            status: 状态。
            is_top: 是否置顶。
            source: 来源。
            package_id: 包版本主键。
            source_key: 包内稳定键。
            generated_by: 生成方式。
            ai_model: AI 模型。
            reviewed_by: 审核人。

        Returns:
            SysHelpArticle: 新行。
        """
        row = SysHelpArticle(
            category_id=category_id,
            title=title,
            content=content,
            status=status,
            is_top=is_top,
            source=source,
            package_id=package_id,
            source_key=source_key,
            local_override=False,
            generated_by=generated_by,
            ai_model=ai_model,
            reviewed_by=reviewed_by,
            publish_at=_utc_now() if status == ARTICLE_STATUS_PUBLISHED else None,
            view_count=0,
            helpful_count=0,
            unhelpful_count=0,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_article(
        self,
        row: SysHelpArticle,
        *,
        category_id: int,
        title: str,
        content: str,
        status: str,
        is_top: bool,
        package_id: int,
        generated_by: str,
        ai_model: str | None,
        reviewed_by: str | None,
    ) -> None:
        """更新包来源文章（不碰计数 / 作者 / 本地覆盖标记）。

        Args:
            row: 文章行。
            category_id: 分类主键。
            title: 默认语言标题。
            content: 默认语言正文。
            status: 状态。
            is_top: 是否置顶。
            package_id: 包版本主键。
            generated_by: 生成方式。
            ai_model: AI 模型。
            reviewed_by: 审核人。
        """
        row.category_id = category_id
        row.title = title
        row.content = content
        row.status = status
        row.is_top = is_top
        row.package_id = package_id
        row.generated_by = generated_by
        row.ai_model = ai_model
        row.reviewed_by = reviewed_by
        if status == ARTICLE_STATUS_PUBLISHED and row.publish_at is None:
            row.publish_at = _utc_now()
        await self._session.flush()

    async def replace_targets(self, article_id: int, targets: ConcurrentStableFrozenList[tuple[str, str]]) -> None:
        """整体替换文章目标（旧行软删、按新集合插行）。

        Args:
            article_id: 文章主键。
            targets: [(类型, 键)]。
        """
        statement = select(SysHelpArticleTarget).where(
            SysHelpArticleTarget.article_id == article_id,
            SysHelpArticleTarget.deleted_at.is_(None),
        )
        for row in (await self._session.execute(statement)).scalars().all():
            row.soft_delete()
        for target_type, target_key in targets:
            self._session.add(
                SysHelpArticleTarget(article_id=article_id, target_type=target_type, target_key=target_key)
            )
        await self._session.flush()

    async def replace_i18n(self, article_id: int, locales: ConcurrentStableFrozenDict[str, tuple[str, str]]) -> None:
        """整体替换文章多语言文案。

        Args:
            article_id: 文章主键。
            locales: 语言 → (标题, 正文)。
        """
        texts: ConcurrentStableDict[str, ConcurrentStableDict[str, str]] = ConcurrentStableDict()
        for locale, (title, content) in locales.items():
            texts.set(locale, ConcurrentStableDict({"title": title, "content": content}))
        await replace_i18n_texts(
            self._session,
            SysHelpArticleI18n,
            "article_id",
            article_id,
            texts,
            text_columns=_ARTICLE_TEXT_COLUMNS,
        )

    async def offline_article(self, row: SysHelpArticle) -> None:
        """把文章置为已下架（保留行与包归属）。

        Args:
            row: 文章行。
        """
        if row.status != "offline":
            row.status = "offline"
            await self._session.flush()

    # ---- 解析读面 ----

    async def default_locale(self) -> str:
        """取租户默认语言（缺失回退出厂默认）。

        Returns:
            str: 默认语言标识。
        """
        return await load_help_default_locale(self._session)

    async def resolve(self, query: HelpContentQuery) -> HelpContentResult:
        """按候选顺序解析帮助内容（未命中返回空结果 + 顶层分类）。

        Args:
            query: 解析请求（候选有序）。

        Returns:
            HelpContentResult: 解析结果。
        """
        default_locale = await self.default_locale()
        locales = ConcurrentStableList((normalize_locale(query.locale), default_locale))
        for candidate in query.candidates:
            target_type = _LEVEL_TARGET_TYPES.get(candidate.level)
            if target_type is None:
                continue
            rows = await self._target_articles(target_type, candidate.help_key or "")
            if not rows:
                continue
            primary, related = rows[0], rows[1:]
            texts = await load_i18n_texts(
                self._session,
                SysHelpArticleI18n,
                "article_id",
                ConcurrentStableList([primary.id, *[row.id for row in related]]),
                locales=locales,
                text_columns=_ARTICLE_TEXT_COLUMNS,
            )
            article = _article_from(primary, texts.get(int(primary.id)))
            summaries = ConcurrentStableList(_summary_from(row, texts.get(int(row.id))) for row in related)
            categories = await self._category_chain(int(primary.category_id))
            return HelpContentResult(
                level=candidate.level,
                help_key=candidate.help_key,
                article=article,
                related=ConcurrentStableFrozenList(summaries),
                categories=categories,
            )
        categories = await self._top_categories()
        return HelpContentResult(categories=categories)

    async def _target_articles(self, target_type: str, target_key: str) -> ConcurrentStableList[SysHelpArticle]:
        """取某目标下已发布文章（按来源优先级 / 包版本 / 主键排序）。

        Args:
            target_type: 目标类型。
            target_key: 目标键（global 为空串）。

        Returns:
            ConcurrentStableList[SysHelpArticle]: 排序后的文章行。
        """
        statement = (
            select(SysHelpArticle, SysHelpPackage)
            .join(SysHelpArticleTarget, SysHelpArticleTarget.article_id == SysHelpArticle.id)
            .outerjoin(SysHelpPackage, SysHelpPackage.id == SysHelpArticle.package_id)
            .where(
                SysHelpArticleTarget.target_type == target_type,
                SysHelpArticleTarget.target_key == target_key,
                SysHelpArticleTarget.deleted_at.is_(None),
                SysHelpArticle.status == ARTICLE_STATUS_PUBLISHED,
                SysHelpArticle.deleted_at.is_(None),
            )
        )
        rows = (await self._session.execute(statement)).all()
        ordered = ConcurrentStableList(rows).sorted(
            key=lambda item: (
                SOURCE_PRIORITY.get(str(item[0].source), len(SOURCE_PRIORITY)),
                _version_key(item[1].package_version if item[1] is not None else ""),
                int(item[0].id),
            )
        )
        return ConcurrentStableList(item[0] for item in ordered)

    async def _category_chain(self, category_id: int) -> ConcurrentStableFrozenList[HelpCategory]:
        """取分类的根 → 叶链路（供命中时定位分类导航）。

        Args:
            category_id: 分类主键。

        Returns:
            ConcurrentStableFrozenList[HelpCategory]: 分类摘要链路（断链时返回已有部分）。
        """
        categories = await self.load_categories()
        by_id = ConcurrentStableDict((int(row.id), row) for row in categories)
        chain: ConcurrentStableList[HelpCategory] = ConcurrentStableList()
        current = by_id.get(category_id)
        seen: ConcurrentStableList[int] = ConcurrentStableList()
        while current is not None and int(current.id) not in seen:
            seen.add(int(current.id))
            chain.add(HelpCategory(category_id=int(current.id), name=str(current.name), path=""))
            parent_id = int(current.parent_id)
            current = by_id.get(parent_id) if parent_id != 0 else None
        ordered = ConcurrentStableFrozenList(reversed(chain))
        path_parts: ConcurrentStableList[str] = ConcurrentStableList()
        rebuilt: ConcurrentStableList[HelpCategory] = ConcurrentStableList()
        for item in ordered:
            path_parts.add(item.name)
            rebuilt.add(HelpCategory(category_id=item.category_id, name=item.name, path="/".join(path_parts)))
        return ConcurrentStableFrozenList(rebuilt)

    async def _top_categories(self) -> ConcurrentStableFrozenList[HelpCategory]:
        """取顶层分类（未命中兜底列表）。

        Returns:
            ConcurrentStableFrozenList[HelpCategory]: 顶层分类摘要。
        """
        statement = (
            select(SysHelpCategory)
            .where(
                SysHelpCategory.parent_id == 0,
                SysHelpCategory.status == "enabled",
                SysHelpCategory.deleted_at.is_(None),
            )
            .order_by(SysHelpCategory.sort, SysHelpCategory.id)
            .limit(_MAX_MISS_CATEGORIES)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return ConcurrentStableFrozenList(
            HelpCategory(category_id=int(row.id), name=str(row.name), path=str(row.name)) for row in rows
        )


def _version_key(value: str) -> tuple[int, int, int]:
    """把包版本转排序键（非法 / 空版本排最后）。

    Args:
        value: 版本字符串。

    Returns:
        tuple[int, int, int]: 排序键。
    """
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return -1, -1, -1
    return int(parts[0]), int(parts[1]), int(parts[2])


def _texts(text: object) -> tuple[str | None, str | None]:
    """从 i18n 文案映射取标题 / 正文。

    Args:
        text: `I18nTextMap` 或 None。

    Returns:
        tuple[str | None, str | None]: (标题, 正文)。
    """
    if text is None:
        return None, None
    mapping = cast_mapping(text)
    return mapping.get("title"), mapping.get("content")


def cast_mapping(value: object) -> ConcurrentStableDict[str, str]:
    """把对象规整为文案映射（运行期已是插入序字典）。

    Args:
        value: 原始值。

    Returns:
        ConcurrentStableDict[str, str]: 文案映射。
    """
    if isinstance(value, ConcurrentStableDict):
        return cast("ConcurrentStableDict[str, str]", value)
    if isinstance(value, dict):
        return ConcurrentStableDict[str, str](cast("dict[str, str]", value))
    return ConcurrentStableDict[str, str]()


def _article_from(row: SysHelpArticle, text: object) -> HelpArticle:
    """文章行 + 语言文案 → 命中文章值对象。

    Args:
        row: 文章行。
        text: 语言文案映射（None 表示两级回退皆缺）。

    Returns:
        HelpArticle: 命中文章。
    """
    title, content = _texts(text)
    return HelpArticle(
        article_id=int(row.id),
        title=title or str(row.title),
        content=content or str(row.content),
        source=str(row.source),
    )


def _summary_from(row: SysHelpArticle, text: object) -> HelpArticleSummary:
    """文章行 + 语言文案 → 相关内容摘要。

    Args:
        row: 文章行。
        text: 语言文案映射。

    Returns:
        HelpArticleSummary: 摘要。
    """
    title, _content = _texts(text)
    return HelpArticleSummary(article_id=int(row.id), title=title or str(row.title), source=str(row.source))


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，落 DATETIME）。

    Returns:
        datetime: UTC 当前时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)
