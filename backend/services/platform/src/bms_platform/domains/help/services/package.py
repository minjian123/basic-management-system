"""帮助包装载 / 卸载服务：计划器 + 执行器（08_03）。

口径（详细设计 §5.4 / §5.5）：

- 同一计划器同时服务 dry-run 与实跑，计数必然一致；
- 同版本 + 同校验和 + 当前版本 = 零变更（不修正租户手工下线的文章）；
- 同版本不同校验和 / 低版本 = 拒收；包内移除只置 `offline`，再次出现恢复；
- `local_override=true` 整篇跳过（包内移除仍下线）；
- 目标冲突：高优先级占位则跳过；同优先级跨产品跳过；`builtin` 可覆盖 `product` / `tenant`；
- 分类按路径 upsert，已存在只更新 `sort`，不改其下文章。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.exceptions import (
    HelpCategoryPathUnresolvedError,
    HelpPackageInvalidError,
    HelpPackageNotLoadedError,
    HelpPackageVersionConflictError,
)
from bms_core.core.objects import BaseValueObject
from bms_core.db.session import DbSession
from bms_core.help.anchors import HelpAnchorKind
from bms_core.help.values import (
    ARTICLE_STATUS_OFFLINE,
    ARTICLE_STATUS_PUBLISHED,
    PACKAGE_STATUS_LOADED,
    SOURCE_PRIORITY,
)
from bms_core.models.platform.help import SysHelpArticle, SysHelpPackage
from bms_platform.domains.help.package_spec import (
    HelpArticleSpec,
    HelpCategorySpec,
    HelpPackageSpec,
    filter_for_tenant,
    filter_unknown_targets,
    parse_version,
)
from bms_platform.domains.help.repositories.content import (
    HelpArticleRecord,
    HelpContentRepository,
    HelpTargetOccupancy,
)

__all__ = [
    "HelpLoadCounts",
    "HelpLoadOutcome",
    "HelpPackageService",
    "HelpUnloadCounts",
    "HelpUnloadOutcome",
]

_ACTION_UNCHANGED = "unchanged"
_ACTION_CREATED = "created"
_ACTION_UPGRADED = "upgraded"
_ACTION_RESTORED = "restored"


@dataclass(frozen=True)
class HelpLoadCounts(BaseValueObject):
    """一次装载的计数快照（dry-run 与实跑共用）。"""

    articles_new: int = 0
    articles_updated: int = 0
    articles_offline: int = 0
    articles_skipped_override: int = 0
    articles_skipped_conflict: int = 0
    articles_unchanged: int = 0
    categories_created: int = 0
    categories_updated: int = 0
    categories_unchanged: int = 0

    @property
    def articles_skipped(self) -> int:
        """跳过总数（本地覆盖 + 目标冲突）。

        Returns:
            int: 跳过条数。
        """
        return self.articles_skipped_override + self.articles_skipped_conflict


@dataclass(frozen=True)
class HelpLoadOutcome(BaseValueObject):
    """一次装载的结果。

    Attributes:
        counts: 计数快照。
        package_action: `unchanged` / `created` / `upgraded` / `restored`。
        warnings: 宽松模式跳过的文章告警。
        applied: 是否已写库（False = dry-run）。
    """

    counts: HelpLoadCounts
    package_action: str
    warnings: ConcurrentStableFrozenList[str] = field(default_factory=lambda: ConcurrentStableFrozenList())
    applied: bool = False


@dataclass(frozen=True)
class HelpUnloadCounts(BaseValueObject):
    """一次卸载的计数快照。"""

    articles_offline: int = 0
    articles_unchanged: int = 0
    packages_unloaded: int = 0


@dataclass(frozen=True)
class HelpUnloadOutcome(BaseValueObject):
    """一次卸载的结果。

    Attributes:
        counts: 计数快照。
        applied: 是否已写库（False = dry-run）。
    """

    counts: HelpUnloadCounts
    applied: bool = False


@dataclass(frozen=True)
class _LoadPlan(BaseValueObject):
    """装载计划（内部值对象；dry-run 只读它，实跑执行它）。"""

    package_action: str
    package_id: int | None
    package_version: str
    schema_version: int
    checksum: str
    article_count: int
    generated_at: datetime | None
    source: str
    categories_new: ConcurrentStableList[HelpCategorySpec]
    categories_updated: ConcurrentStableList[tuple[int, int]]
    categories_unchanged: int
    articles_new: ConcurrentStableList[HelpArticleSpec]
    articles_updated: ConcurrentStableList[tuple[int, HelpArticleSpec]]
    offline_ids: ConcurrentStableList[int]
    skipped_override: ConcurrentStableList[str]
    skipped_conflict: ConcurrentStableList[str]
    articles_unchanged: int
    warnings: ConcurrentStableFrozenList[str]

    @property
    def counts(self) -> HelpLoadCounts:
        """计划计数。

        Returns:
            HelpLoadCounts: 计数快照。
        """
        return HelpLoadCounts(
            articles_new=len(self.articles_new),
            articles_updated=len(self.articles_updated),
            articles_offline=len(self.offline_ids),
            articles_skipped_override=len(self.skipped_override),
            articles_skipped_conflict=len(self.skipped_conflict),
            articles_unchanged=self.articles_unchanged,
            categories_created=len(self.categories_new),
            categories_updated=len(self.categories_updated),
            categories_unchanged=self.categories_unchanged,
        )


class HelpPackageService:
    """帮助包装载 / 卸载服务（单租户库会话）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话（写路径由调用方开事务）。
        """
        self._repo = HelpContentRepository(session)

    async def load(
        self,
        spec: HelpPackageSpec,
        *,
        anchors: ConcurrentStableDict[str, HelpAnchorKind],
        apply: bool,
        lenient: bool,
    ) -> HelpLoadOutcome:
        """装载或升级帮助包。

        Args:
            spec: 已通过文件层校验的包规格。
            anchors: 平台锚点清单（`help_key` → 节点类型）。
            apply: 是否写库（False = dry-run）。
            lenient: 是否跳过无效文章。

        Returns:
            HelpLoadOutcome: 计数与包状态迁移。

        Raises:
            HelpPackageVersionConflictError: 同版本不同校验和或低版本（40011）。
            HelpAnchorUnresolvedError: 严格模式下锚点不可解析（40008）。
            HelpPackageInvalidError: 严格模式下默认语言缺失 / 过滤后无有效文章（40009）。
            HelpCategoryPathUnresolvedError: 分类路径不可解析（40013）。
        """
        plan = await self._plan(spec, anchors=anchors, lenient=lenient)
        if apply and plan.package_action != _ACTION_UNCHANGED:
            await self._apply(spec, plan)
        return HelpLoadOutcome(
            counts=plan.counts,
            package_action=plan.package_action,
            warnings=plan.warnings,
            applied=apply,
        )

    async def unload(self, product_key: str, *, apply: bool) -> HelpUnloadOutcome:
        """卸载某产品的全部包来源文章。

        Args:
            product_key: 产品键。
            apply: 是否写库（False = dry-run）。

        Returns:
            HelpUnloadOutcome: 计数。

        Raises:
            HelpPackageNotLoadedError: 该产品没有任何包登记行（40012）。
        """
        packages = await self._repo.load_packages(product_key)
        if not packages:
            raise HelpPackageNotLoadedError(f"帮助包未装载：{product_key}")
        records = await self._repo.load_package_articles(product_key)
        offline = ConcurrentStableList(
            record.article for record in records if record.article.status != ARTICLE_STATUS_OFFLINE
        )
        counts = HelpUnloadCounts(
            articles_offline=len(offline),
            articles_unchanged=len(records) - len(offline),
            packages_unloaded=len(packages),
        )
        if apply:
            await self._repo.unload_packages(product_key)
            for article in offline:
                await self._repo.offline_article(article)
        return HelpUnloadOutcome(counts=counts, applied=apply)

    async def _plan(
        self,
        spec: HelpPackageSpec,
        *,
        anchors: ConcurrentStableDict[str, HelpAnchorKind],
        lenient: bool,
    ) -> _LoadPlan:
        """构建装载计划（不写库）。

        Args:
            spec: 包规格。
            anchors: 平台锚点清单。
            lenient: 是否跳过无效文章。

        Returns:
            _LoadPlan: 计划。

        Raises:
            HelpPackageVersionConflictError: 版本冲突（40011）。
            HelpAnchorUnresolvedError: 锚点不可解析（40008）。
            HelpPackageInvalidError: 默认语言缺失 / 无有效文章（40009）。
            HelpCategoryPathUnresolvedError: 分类路径不可解析（40013）。
        """
        packages = await self._repo.load_packages(spec.product_key)
        current_same = _same_version(packages, spec.package_version)
        if current_same is not None and current_same.checksum != spec.checksum:
            raise HelpPackageVersionConflictError(
                f"同版本校验和不同：{spec.product_key} {spec.package_version}（已装载 {current_same.checksum}）"
            )
        highest = _highest_version(packages)
        if highest is not None and spec.version_tuple < highest:
            highest_text = ".".join(str(part) for part in highest)
            raise HelpPackageVersionConflictError(
                f"不允许降级：{spec.product_key} {spec.package_version} 低于已装载最高版本 {highest_text}"
            )
        if (
            current_same is not None
            and current_same.status == PACKAGE_STATUS_LOADED
            and current_same.checksum == spec.checksum
        ):
            return _LoadPlan(
                package_action=_ACTION_UNCHANGED,
                package_id=int(current_same.id),
                package_version=spec.package_version,
                schema_version=spec.schema_version,
                checksum=spec.checksum,
                article_count=spec.declared_article_count,
                generated_at=spec.generated_at,
                source=spec.source,
                categories_new=ConcurrentStableList(),
                categories_updated=ConcurrentStableList(),
                categories_unchanged=0,
                articles_new=ConcurrentStableList(),
                articles_updated=ConcurrentStableList(),
                offline_ids=ConcurrentStableList(),
                skipped_override=ConcurrentStableList(),
                skipped_conflict=ConcurrentStableList(),
                articles_unchanged=0,
                warnings=spec.warnings,
            )

        filtered = filter_unknown_targets(spec, anchors, lenient=lenient)
        categories = await self._repo.load_categories()
        path_map = self._repo.build_path_map(categories)
        existing_paths = ConcurrentStableSet(path_map.values())
        declared_paths = ConcurrentStableSet(category.path for category in filtered.categories)
        self._ensure_category_parents(filtered.categories, existing_paths, declared_paths)
        known_paths = ConcurrentStableSet(existing_paths)
        for path in declared_paths:
            known_paths.add(path)
        tenant_filtered = filter_for_tenant(
            filtered,
            default_locale=await self._repo.default_locale(),
            category_paths=known_paths,
            lenient=lenient,
        )
        if filtered.declared_article_count > 0 and not tenant_filtered.articles:
            raise HelpPackageInvalidError("宽松模式过滤后无有效文章，拒绝装载（避免误下线全部文章）")

        records = await self._repo.load_package_articles(spec.product_key)
        existing_by_key = _records_by_source_key(records)
        spec_keys = ConcurrentStableSet(article.source_key for article in tenant_filtered.articles)
        offline_records = ConcurrentStableList(
            record
            for key, record in existing_by_key.items()
            if key not in spec_keys and record.article.status != ARTICLE_STATUS_OFFLINE
        )
        offline_ids = ConcurrentStableList(int(record.article.id) for record in offline_records)

        existing_ids = ConcurrentStableList(
            int(record.article.id) for key, record in existing_by_key.items() if key in spec_keys
        )
        targets_map = await self._repo.load_article_targets(existing_ids)
        i18n_map = await self._repo.load_article_i18n(existing_ids)
        pairs = ConcurrentStableList(
            (target.target_type, target.target_key)
            for article in tenant_filtered.articles
            for target in article.targets
        )
        occupancy = await self._repo.load_target_occupancy(pairs)
        default_locale = await self._repo.default_locale()

        categories_new: ConcurrentStableList[HelpCategorySpec] = ConcurrentStableList()
        categories_updated: ConcurrentStableList[tuple[int, int]] = ConcurrentStableList()
        categories_unchanged = 0
        existing_by_path = ConcurrentStableDict((path, model_id) for model_id, path in path_map.items())
        for category in filtered.categories:
            model_id = existing_by_path.get(category.path)
            if model_id is None:
                categories_new.add(category)
                continue
            existing = next(row for row in categories if int(row.id) == model_id)
            if int(existing.sort) != category.sort:
                categories_updated.add((model_id, category.sort))
            else:
                categories_unchanged += 1

        articles_new: ConcurrentStableList[HelpArticleSpec] = ConcurrentStableList()
        articles_updated: ConcurrentStableList[tuple[int, HelpArticleSpec]] = ConcurrentStableList()
        skipped_override: ConcurrentStableList[str] = ConcurrentStableList()
        skipped_conflict: ConcurrentStableList[str] = ConcurrentStableList()
        unchanged = 0
        for article in tenant_filtered.articles:
            existing = existing_by_key.get(article.source_key)
            if existing is not None:
                differs = _article_differs(
                    existing.article,
                    article,
                    default_locale=default_locale,
                    path_map=path_map,
                    targets_map=targets_map,
                    i18n_map=i18n_map,
                )
                if existing.article.local_override:
                    if differs:
                        skipped_override.add(article.source_key)
                    else:
                        unchanged += 1
                    continue
                if _conflicts(
                    article,
                    occupancy=occupancy,
                    offline_ids=offline_ids,
                    existing_id=int(existing.article.id),
                    product_key=spec.product_key,
                    source=spec.source,
                ):
                    skipped_conflict.add(article.source_key)
                    continue
                if differs:
                    articles_updated.add((int(existing.article.id), article))
                else:
                    unchanged += 1
                continue
            if _conflicts(
                article,
                occupancy=occupancy,
                offline_ids=offline_ids,
                existing_id=None,
                product_key=spec.product_key,
                source=spec.source,
            ):
                skipped_conflict.add(article.source_key)
                continue
            articles_new.add(article)

        action = _ACTION_RESTORED if current_same is not None else (_ACTION_UPGRADED if packages else _ACTION_CREATED)
        return _LoadPlan(
            package_action=action,
            package_id=int(current_same.id) if current_same is not None else None,
            package_version=spec.package_version,
            schema_version=spec.schema_version,
            checksum=spec.checksum,
            article_count=spec.declared_article_count,
            generated_at=spec.generated_at,
            source=spec.source,
            categories_new=categories_new,
            categories_updated=categories_updated,
            categories_unchanged=categories_unchanged,
            articles_new=articles_new,
            articles_updated=articles_updated,
            offline_ids=offline_ids,
            skipped_override=skipped_override,
            skipped_conflict=skipped_conflict,
            articles_unchanged=unchanged,
            warnings=tenant_filtered.warnings,
        )

    async def _apply(self, spec: HelpPackageSpec, plan: _LoadPlan) -> None:
        """执行装载计划（调用方负责事务）。

        Args:
            spec: 包规格。
            plan: 计划。
        """
        package = await self._ensure_package(spec, plan)
        await self._repo.outdate_other_packages(spec.product_key, int(package.id))
        default_locale = await self._repo.default_locale()

        categories = await self._repo.load_categories()
        path_to_id: ConcurrentStableDict[str, int] = ConcurrentStableDict(
            (path, model_id) for model_id, path in self._repo.build_path_map(categories).items()
        )
        for category in spec.categories:
            model_id = path_to_id.get(category.path)
            if model_id is None:
                parent_path = category.path.rsplit("/", 1)[0] if "/" in category.path else None
                parent_id = path_to_id.get(parent_path) if parent_path is not None else 0
                if parent_id is None:
                    raise HelpCategoryPathUnresolvedError(f"分类父级不可解析：{category.path}")
                row = await self._repo.create_category(
                    name=category.path.rsplit("/", 1)[-1],
                    parent_id=parent_id,
                    sort=category.sort,
                )
                path_to_id.set(category.path, int(row.id))
                continue
            if any(existing_id == model_id for existing_id, _sort in plan.categories_updated):
                row = next(item for item in categories if int(item.id) == model_id)
                await self._repo.update_category_sort(row, category.sort)

        updated_by_id: ConcurrentStableDict[int, HelpArticleSpec] = ConcurrentStableDict(plan.articles_updated)
        for article in plan.articles_new:
            category_id = path_to_id.get(article.category_path)
            if category_id is None:
                raise HelpCategoryPathUnresolvedError(f"文章分类不可解析：{article.source_key} {article.category_path}")
            row = await self._repo.create_article(
                category_id=category_id,
                title=_default_title(article, default_locale),
                content=_default_content(article, default_locale),
                status=article.status,
                is_top=article.is_top,
                source=spec.source,
                package_id=int(package.id),
                source_key=article.source_key,
                generated_by=article.provenance.author,
                ai_model=article.provenance.model,
                reviewed_by=article.provenance.reviewed_by,
            )
            await self._repo.replace_targets(int(row.id), _targets(article))
            await self._repo.replace_i18n(int(row.id), _locales(article))

        for article_id, article in updated_by_id.items():
            category_id = path_to_id.get(article.category_path)
            if category_id is None:
                raise HelpCategoryPathUnresolvedError(f"文章分类不可解析：{article.source_key} {article.category_path}")
            row = await self._repo.get_article(article_id)
            await self._repo.update_article(
                row,
                category_id=category_id,
                title=_default_title(article, default_locale),
                content=_default_content(article, default_locale),
                status=article.status,
                is_top=article.is_top,
                package_id=int(package.id),
                generated_by=article.provenance.author,
                ai_model=article.provenance.model,
                reviewed_by=article.provenance.reviewed_by,
            )
            await self._repo.replace_targets(article_id, _targets(article))
            await self._repo.replace_i18n(article_id, _locales(article))

        for article_id in plan.offline_ids:
            row = await self._repo.get_article(article_id)
            await self._repo.offline_article(row)

    async def _ensure_package(self, spec: HelpPackageSpec, plan: _LoadPlan) -> SysHelpPackage:
        """取 / 建包登记行。

        Args:
            spec: 包规格。
            plan: 计划。

        Returns:
            SysHelpPackage: 当前版本行。
        """
        if plan.package_id is None:
            return await self._repo.create_package(
                product_key=spec.product_key,
                package_version=spec.package_version,
                schema_version=spec.schema_version,
                checksum=spec.checksum,
                article_count=spec.declared_article_count,
                generated_at=spec.generated_at,
            )
        row = await self._repo.get_package(plan.package_id)
        await self._repo.mark_package_loaded(
            row,
            checksum=spec.checksum,
            article_count=spec.declared_article_count,
            generated_at=spec.generated_at,
        )
        return row

    @staticmethod
    def _ensure_category_parents(
        categories: ConcurrentStableFrozenList[HelpCategorySpec],
        existing_paths: ConcurrentStableSet[str],
        declared_paths: ConcurrentStableSet[str],
    ) -> None:
        """校验声明分类的每一级父路径都能在「包内声明或租户既有」中找到。

        Args:
            categories: 声明分类。
            existing_paths: 租户既有分类路径。
            declared_paths: 包内声明路径。

        Raises:
            HelpCategoryPathUnresolvedError: 存在无法解析的父路径（40013）。
        """
        for category in categories:
            for prefix in _prefixes(category.path):
                if prefix not in existing_paths and prefix not in declared_paths:
                    raise HelpCategoryPathUnresolvedError(f"分类路径不可解析：{category.path}（缺少 {prefix}）")


def _prefixes(path: str) -> ConcurrentStableList[str]:
    """取路径的逐级前缀（含完整路径）。

    Args:
        path: `/` 分隔路径。

    Returns:
        ConcurrentStableList[str]: 前缀序列。
    """
    parts = path.split("/")
    prefixes: ConcurrentStableList[str] = ConcurrentStableList()
    current: ConcurrentStableList[str] = ConcurrentStableList()
    for part in parts:
        current.add(part)
        prefixes.add("/".join(current))
    return prefixes


def _same_version(packages: ConcurrentStableList[SysHelpPackage], version: str) -> SysHelpPackage | None:
    """取同版本包行。

    Args:
        packages: 包行。
        version: 版本字符串。

    Returns:
        SysHelpPackage | None: 同版本行。
    """
    for row in packages:
        if str(row.package_version) == version:
            return row
    return None


def _highest_version(packages: ConcurrentStableList[SysHelpPackage]) -> tuple[int, int, int] | None:
    """取已装载最高版本。

    Args:
        packages: 包行。

    Returns:
        tuple[int, int, int] | None: 最高版本元组。
    """
    versions: ConcurrentStableList[tuple[int, int, int]] = ConcurrentStableList(
        parse_version(str(row.package_version)) for row in packages
    )
    return max(versions) if versions else None


def _records_by_source_key(
    records: ConcurrentStableList[HelpArticleRecord],
) -> ConcurrentStableDict[str, HelpArticleRecord]:
    """按 `source_key` 归集包来源文章（同键取最高包版本）。

    Args:
        records: 包来源文章记录。

    Returns:
        ConcurrentStableDict[str, HelpArticleRecord]: source_key → 记录。
    """
    result: ConcurrentStableDict[str, HelpArticleRecord] = ConcurrentStableDict()
    for record in records:
        key = record.article.source_key
        if not key:
            continue
        current = result.get(str(key))
        if current is None or parse_version(record.package_version) >= parse_version(current.package_version):
            result.set(str(key), record)
    return result


def _article_differs(
    row: SysHelpArticle,
    spec: HelpArticleSpec,
    *,
    default_locale: str,
    path_map: ConcurrentStableDict[int, str],
    targets_map: ConcurrentStableDict[int, ConcurrentStableFrozenList[tuple[str, str]]],
    i18n_map: ConcurrentStableDict[int, ConcurrentStableFrozenDict[str, tuple[str, str]]],
) -> bool:
    """判断文章是否需要更新。

    Args:
        row: 现有文章行。
        spec: 期望文章。
        default_locale: 租户默认语言。
        path_map: 分类主键 → 路径。
        targets_map: 文章 → 目标集合。
        i18n_map: 文章 → 语言文案。

    Returns:
        bool: 有差异为 True。
    """
    text = spec.locales.get(default_locale)
    if text is None:
        return True
    if (
        str(row.title) != text.title
        or str(row.content) != text.content
        or str(row.status) != spec.status
        or bool(row.is_top) != spec.is_top
        or str(row.generated_by) != spec.provenance.author
        or (row.ai_model or None) != spec.provenance.model
        or (row.reviewed_by or None) != spec.provenance.reviewed_by
        or path_map.get(int(row.category_id)) != spec.category_path
        or (spec.status == ARTICLE_STATUS_PUBLISHED and row.publish_at is None)
    ):
        return True
    existing_targets = set(targets_map.get(int(row.id), ConcurrentStableFrozenList()))
    if existing_targets != {(target.target_type, target.target_key) for target in spec.targets}:
        return True
    existing_i18n = dict(i18n_map.get(int(row.id), ConcurrentStableFrozenDict[str, tuple[str, str]]()).items())
    desired_i18n = {locale: (text.title, text.content) for locale, text in spec.locales.items()}
    return existing_i18n != desired_i18n


def _conflicts(
    article: HelpArticleSpec,
    *,
    occupancy: ConcurrentStableDict[tuple[str, str], ConcurrentStableList[HelpTargetOccupancy]],
    offline_ids: ConcurrentStableList[int],
    existing_id: int | None,
    product_key: str,
    source: str,
) -> bool:
    """判断文章的目标是否被更高 / 同等优先级来源占用。

    Args:
        article: 待装载文章。
        occupancy: 目标占用清单。
        offline_ids: 本次将下线的文章主键（不参与冲突）。
        existing_id: 同 `source_key` 的现有文章主键（其自身占用不算冲突）。
        product_key: 包产品键。
        source: 文章来源。

    Returns:
        bool: 冲突为 True。
    """
    new_priority = SOURCE_PRIORITY.get(source, len(SOURCE_PRIORITY))
    for target in article.targets:
        for occupied in occupancy.get((target.target_type, target.target_key), ConcurrentStableList()):
            if occupied.article_id in offline_ids:
                continue
            if existing_id is not None and occupied.article_id == existing_id:
                continue
            if occupied.source_key == article.source_key and occupied.product_key == product_key:
                continue
            occupied_priority = SOURCE_PRIORITY.get(occupied.source, len(SOURCE_PRIORITY))
            if occupied_priority < new_priority:
                return True
            if occupied_priority == new_priority and occupied.product_key != product_key:
                return True
            if (
                occupied_priority == new_priority
                and occupied.product_key == product_key
                and occupied.source_key != article.source_key
            ):
                return True
    return False


def _default_title(article: HelpArticleSpec, default_locale: str) -> str:
    """取默认语言标题（缺失时取首个语言）。

    Args:
        article: 文章规格。
        default_locale: 租户默认语言。

    Returns:
        str: 标题。
    """
    text = article.locales.get(default_locale)
    if text is not None:
        return text.title
    return next(iter(article.locales.values())).title


def _default_content(article: HelpArticleSpec, default_locale: str) -> str:
    """取默认语言正文（缺失时取首个语言）。

    Args:
        article: 文章规格。
        default_locale: 租户默认语言。

    Returns:
        str: 正文。
    """
    text = article.locales.get(default_locale)
    if text is not None:
        return text.content
    return next(iter(article.locales.values())).content


def _targets(article: HelpArticleSpec) -> ConcurrentStableFrozenList[tuple[str, str]]:
    """取文章目标对。

    Args:
        article: 文章规格。

    Returns:
        ConcurrentStableFrozenList[tuple[str, str]]: [(类型, 键)]。
    """
    return ConcurrentStableFrozenList((target.target_type, target.target_key) for target in article.targets)


def _locales(article: HelpArticleSpec) -> ConcurrentStableFrozenDict[str, tuple[str, str]]:
    """取文章语言文案对。

    Args:
        article: 文章规格。

    Returns:
        ConcurrentStableFrozenDict[str, tuple[str, str]]: 语言 → (标题, 正文)。
    """
    return ConcurrentStableFrozenDict((locale, (text.title, text.content)) for locale, text in article.locales.items())
