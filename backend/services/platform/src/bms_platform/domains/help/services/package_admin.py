"""帮助包管理面服务：列表 / 装载 / 卸载（12_01，复用 08_03 计划器）。

- **受限目录**：`package_path` 只接受 `[help_package].root` 内的相对路径；绝对路径、`..` 越界、
  不存在一律 `40021`；
- **同一计划器**：`dry_run=true` 等价命令行不带 `--apply`，计数与实跑一致；
- **只装当前租户**：HTTP 请求按租户上下文写当前租户库；`--all-tenants` 仍归命令行；
- **锚点清单**：从平台库归集（与命令行同源），用于装载期目标校验。
"""

from __future__ import annotations

from pathlib import Path

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import get_current_tenant
from bms_core.core.exceptions import HelpPackagePathInvalidError, ParamError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.help.anchors import HelpAnchorKind
from bms_core.help.cache import bump_content_version
from bms_core.models.platform.help import SysHelpPackage
from bms_core.repositories.help_anchor import list_help_anchors
from bms_platform.domains.help.package_spec import HelpPackageSpec, load_package
from bms_platform.domains.help.repositories.maintenance import HelpArticleMaintenanceRepository
from bms_platform.domains.help.schemas.package import (
    HelpPackageItem,
    HelpPackageLoadCounts,
    HelpPackageLoadResult,
    HelpPackagePage,
    HelpPackageUnloadCounts,
    HelpPackageUnloadResult,
)
from bms_platform.domains.help.services.package import (
    HelpLoadOutcome,
    HelpPackageService,
    HelpUnloadOutcome,
)

__all__ = ["HelpPackageAdminService"]


class HelpPackageAdminService(BaseFrameworkObject):
    """帮助包管理面服务（单租户）。"""

    def __init__(
        self,
        *,
        session: DbSession,
        platform_session: DbSession,
        uow: UnitOfWork,
        cache: CacheRegion,
        root: str,
    ) -> None:
        """初始化。

        Args:
            session: 租户库会话（内容表）。
            platform_session: 平台库会话（锚点清单）。
            uow: 请求级工作单元（写事务）。
            cache: 缓存 Region（内容版本键）。
            root: 允许装载的根目录（`[help_package].root`）。
        """
        self._session = session
        self._platform_session = platform_session
        self._uow = uow
        self._cache = cache
        self._root = Path(root)
        self._repo = HelpArticleMaintenanceRepository(session)
        self._tenant = get_current_tenant()

    async def list_packages(
        self,
        *,
        product_key: str | None,
        status: str | None,
        page: int,
        size: int,
    ) -> HelpPackagePage:
        """帮助包登记列表。

        Args:
            product_key: 产品键筛选。
            status: 包状态筛选。
            page: 页码。
            size: 每页条数。

        Returns:
            HelpPackagePage: 分页结果。
        """
        rows, total = await self._repo.list_packages(
            product_key=product_key,
            status=status,
            offset=(page - 1) * size,
            limit=size,
        )
        return HelpPackagePage(
            list=ConcurrentStableList(self._item(row) for row in rows),
            total=total,
            page=page,
            size=size,
        )

    async def load(
        self,
        *,
        package_path: str,
        dry_run: bool,
        lenient: bool,
    ) -> HelpPackageLoadResult:
        """装载或升级帮助包。

        Args:
            package_path: 根目录内的相对路径（目录或 package.yaml）。
            dry_run: 是否只预演。
            lenient: 是否跳过无效文章。

        Returns:
            HelpPackageLoadResult: 装载结果。

        Raises:
            HelpPackagePathInvalidError: 路径越界 / 绝对路径 / 不存在（`40021`）。
            HelpPackageVersionConflictError: 同版本不同校验和或低版本（`40011`）。
            HelpAnchorUnresolvedError: 锚点不可解析（`40008`）。
            HelpPackageInvalidError: 结构非法（`40009`）。
            HelpPackageChecksumMismatchError: 校验和不符（`40010`）。
        """
        spec = load_package(self._resolve_path(package_path), lenient=lenient)
        anchors = await self._anchors()
        await self._uow.rollback()
        async with self._uow.begin():
            outcome = await HelpPackageService(self._session).load(
                spec,
                anchors=anchors,
                apply=not dry_run,
                lenient=lenient,
            )
            if outcome.applied and outcome.package_action != "unchanged":
                await bump_content_version(self._cache, tenant=self._tenant)
            return _load_result(spec, outcome)

    async def unload(self, *, product_key: str, dry_run: bool) -> HelpPackageUnloadResult:
        """卸载某产品的帮助包。

        Args:
            product_key: 产品键。
            dry_run: 是否只预演。

        Returns:
            HelpPackageUnloadResult: 卸载结果。

        Raises:
            HelpPackageNotLoadedError: 该产品未装载（`40012`）。
        """
        product = product_key.strip()
        if not product:
            raise ParamError("产品键不能为空")
        await self._uow.rollback()
        async with self._uow.begin():
            outcome = await HelpPackageService(self._session).unload(product, apply=not dry_run)
            if outcome.applied and (outcome.counts.articles_offline or outcome.counts.packages_unloaded):
                await bump_content_version(self._cache, tenant=self._tenant)
            return _unload_result(outcome)

    def _resolve_path(self, package_path: str) -> Path:
        """把入参解析为根目录内的实际路径（越界 / 不存在拒绝）。

        Args:
            package_path: 相对路径。

        Returns:
            Path: 包目录或 package.yaml 路径。

        Raises:
            HelpPackagePathInvalidError: 绝对路径、越界、根目录本身或不存在（`40021`）。
        """
        raw = Path(package_path)
        if raw.is_absolute():
            raise HelpPackagePathInvalidError(f"帮助包路径必须是相对路径：{package_path}")
        root = self._root.resolve()
        candidate = (root / raw).resolve()
        if candidate == root or not candidate.is_relative_to(root):
            raise HelpPackagePathInvalidError(f"帮助包路径越出配置根目录：{package_path}")
        if not candidate.exists():
            raise HelpPackagePathInvalidError(f"帮助包路径不存在：{package_path}")
        return candidate

    async def _anchors(self) -> ConcurrentStableDict[str, HelpAnchorKind]:
        """从平台库归集锚点清单。

        Returns:
            ConcurrentStableDict[str, HelpAnchorKind]: 锚点 → 节点类型。
        """
        anchors: ConcurrentStableDict[str, HelpAnchorKind] = ConcurrentStableDict()
        for entry in await list_help_anchors(self._platform_session):
            anchors.set(entry.help_key, entry.kind)
        return anchors

    def _item(self, row: SysHelpPackage) -> HelpPackageItem:
        """包登记行 → 契约行。

        Args:
            row: 包行。

        Returns:
            HelpPackageItem: 契约行。
        """
        return HelpPackageItem(
            id=int(row.id),
            product_key=str(row.product_key),
            package_version=str(row.package_version),
            schema_version=int(row.schema_version),
            checksum=str(row.checksum),
            article_count=int(row.article_count),
            generated_at=row.generated_at,
            loaded_at=row.loaded_at,
            status=str(row.status),
        )


def _load_result(spec: HelpPackageSpec, outcome: HelpLoadOutcome) -> HelpPackageLoadResult:
    """装载结果 → 契约。

    Args:
        spec: 包规格。
        outcome: 服务结果。

    Returns:
        HelpPackageLoadResult: 契约。
    """
    counts = outcome.counts
    return HelpPackageLoadResult(
        applied=outcome.applied,
        package_action=outcome.package_action,
        product_key=spec.product_key,
        package_version=spec.package_version,
        counts=HelpPackageLoadCounts(
            articles_new=counts.articles_new,
            articles_updated=counts.articles_updated,
            articles_offline=counts.articles_offline,
            articles_skipped=counts.articles_skipped,
            articles_skipped_override=counts.articles_skipped_override,
            articles_skipped_conflict=counts.articles_skipped_conflict,
            articles_unchanged=counts.articles_unchanged,
            categories_created=counts.categories_created,
            categories_updated=counts.categories_updated,
            categories_unchanged=counts.categories_unchanged,
        ),
        warnings=outcome.warnings,
    )


def _unload_result(outcome: HelpUnloadOutcome) -> HelpPackageUnloadResult:
    """卸载结果 → 契约。

    Args:
        outcome: 服务结果。

    Returns:
        HelpPackageUnloadResult: 契约。
    """
    return HelpPackageUnloadResult(
        applied=outcome.applied,
        counts=HelpPackageUnloadCounts(
            articles_offline=outcome.counts.articles_offline,
            articles_unchanged=outcome.counts.articles_unchanged,
            packages_unloaded=outcome.counts.packages_unloaded,
        ),
    )
