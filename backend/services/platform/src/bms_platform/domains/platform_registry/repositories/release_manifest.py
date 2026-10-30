"""发布清单仓储（07C `04_01`）：`sys_release_manifest` / `sys_release_manifest_domain` 读写。

- 归属：两表归 `platform` 服务 × 平台服务库（`bms_platform`），表结构以表文件为准；
- 会话经构造注入；仓储只 `flush` 不 `commit`（事务边界归服务层——主表与明细必须同事务落盘）；
- **不修改历史**：发布行写入后不改（回滚另起一行），故本仓储没有 `update` 语义，只有追加与读取；
- 版本口径：同单元同范围的当前版本 = 未软删除行中的最大 `manifest_version`。
"""

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import ColumnElement, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.release_manifest import (
    RELEASE_STATUS_FAILED,
    RELEASE_STATUS_RELEASED,
    SysReleaseManifest,
    SysReleaseManifestDomain,
)
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery

__all__ = ["ReleaseManifestDomainRepository", "ReleaseManifestRepository"]


class ReleaseManifestRepository(BaseDbRepository[SysReleaseManifest]):
    """发布清单主表仓储（追加 + 读取；事务边界归服务层）。"""

    model = SysReleaseManifest
    sortable_fields = ConcurrentStableSet(
        {"id", "unit_key", "tenant_scope", "manifest_version", "topology_version", "released_at", "status"}
    )

    def _conditions(
        self,
        *,
        unit_key: str | None = None,
        tenant_scope: int | None = None,
        status: str | None = None,
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """构造筛选条件（软删除口径由 `_scope_where` 负责）。

        Args:
            unit_key: 部署单元筛选；None 不过滤。
            tenant_scope: 作用范围筛选；None 不过滤。
            status: 状态筛选；None 不过滤。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if unit_key is not None:
            conditions.add(self._column("unit_key") == unit_key)
        if tenant_scope is not None:
            conditions.add(self._column("tenant_scope") == tenant_scope)
        if status is not None:
            conditions.add(self._column("status") == status)
        return conditions

    async def max_version(self, unit_key: str, tenant_scope: int) -> int:
        """取同单元同范围的当前最大批次号。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。

        Returns:
            int: 最大 `manifest_version`；无记录返回 0。
        """
        statement = select(func.max(self._column("manifest_version"))).where(
            self._column("unit_key") == unit_key,
            self._column("tenant_scope") == tenant_scope,
        )
        return int((await self._session.execute(statement)).scalar_one() or 0)

    async def latest(
        self,
        unit_key: str,
        tenant_scope: int,
        *,
        statuses: Iterable[str] = (RELEASE_STATUS_RELEASED,),
        before_version: int | None = None,
    ) -> SysReleaseManifest | None:
        """取最近一次成功发布（回滚目标定位）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            statuses: 计入的状态集合（缺省只看 `released`）。
            before_version: 只看批次号小于该值的行（回滚时排除当前发布）。

        Returns:
            SysReleaseManifest | None: 最近一次发布；没有返回 None。
        """
        conditions = self._conditions(unit_key=unit_key, tenant_scope=tenant_scope)
        for status in statuses:
            conditions.add(self._column("status") == status)
        if before_version is not None:
            conditions.add(self._column("manifest_version") < before_version)
        statement = self._select().where(*conditions).order_by(self._column("manifest_version").desc()).limit(1)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def find_version(self, unit_key: str, tenant_scope: int, version: int) -> SysReleaseManifest | None:
        """按批次号精确取一行（回滚目标定位）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            version: 批次号。

        Returns:
            SysReleaseManifest | None: 发布行；不存在返回 None。
        """
        conditions = self._conditions(unit_key=unit_key, tenant_scope=tenant_scope)
        conditions.add(self._column("manifest_version") == version)
        statement = self._select().where(*conditions).limit(1)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_recent(
        self, unit_key: str, tenant_scope: int, *, limit: int = 10
    ) -> ConcurrentStableList[SysReleaseManifest]:
        """取某单元最近的若干次发布（管理面查询用）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            limit: 条数上限。

        Returns:
            ConcurrentStableList[SysReleaseManifest]: 发布行（批次号降序）。
        """
        statement = (
            self._select()
            .where(*self._conditions(unit_key=unit_key, tenant_scope=tenant_scope))
            .order_by(self._column("manifest_version").desc())
            .limit(limit)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def page_rows(
        self,
        query: BasePageQuery,
        *,
        unit_key: str | None = None,
        tenant_scope: int | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysReleaseManifest], int]:
        """分页查询发布行（筛选 + 排序 + 当前页 + 筛选后总数）。

        Args:
            query: 页码分页请求（排序经白名单校验、非法忽略）。
            unit_key: 部署单元筛选。
            tenant_scope: 作用范围筛选。
            status: 状态筛选。

        Returns:
            tuple[ConcurrentStableList[SysReleaseManifest], int]: (当前页记录, 筛选后总数)。
        """
        conditions = self._conditions(unit_key=unit_key, tenant_scope=tenant_scope, status=status)
        selectable = self._select().where(*conditions)
        statement = self._apply_sort(selectable, self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        count_statement = select(func.count()).select_from(self.model).where(*conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def create_manifest(
        self,
        *,
        unit_key: str,
        tenant_scope: int,
        manifest_version: int,
        topology_version: int,
        status: str,
        released_at: datetime,
        released_by: int | None,
        rolled_back_from: int | None,
        note: str | None,
    ) -> SysReleaseManifest:
        """追加一次发布（主表一行）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。
            manifest_version: 批次号。
            topology_version: 拓扑版本。
            status: 状态（`released` / `rolled_back` / `failed`）。
            released_at: 发布时间（UTC）。
            released_by: 发布人（自动化为空）。
            rolled_back_from: 回滚来源清单主键（非回滚为空）。
            note: 说明。

        Returns:
            SysReleaseManifest: 落库后的主表行（`id` 已生成）。
        """
        return await self.create(
            unit_key=unit_key,
            tenant_scope=tenant_scope,
            manifest_version=manifest_version,
            topology_version=topology_version,
            status=status,
            released_at=released_at,
            released_by=released_by,
            rolled_back_from=rolled_back_from,
            note=note,
        )

    async def count_failed(self, unit_key: str, tenant_scope: int) -> int:
        """统计某单元范围的失败行数（排查与清理策略用）。

        Args:
            unit_key: 部署单元标识。
            tenant_scope: 作用范围。

        Returns:
            int: 失败行数。
        """
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(*self._conditions(unit_key=unit_key, tenant_scope=tenant_scope, status=RELEASE_STATUS_FAILED))
        )
        return int((await self._session.execute(statement)).scalar_one())


class ReleaseManifestDomainRepository(BaseDbRepository[SysReleaseManifestDomain]):
    """发布清单明细仓储（追加 + 按清单读取）。"""

    model = SysReleaseManifestDomain
    sortable_fields = ConcurrentStableSet({"id", "manifest_id", "domain_key", "created_at", "status"})

    async def list_by_manifest(self, manifest_id: int) -> ConcurrentStableList[SysReleaseManifestDomain]:
        """取某次发布的全部域明细（按域升序）。

        Args:
            manifest_id: 清单主键。

        Returns:
            ConcurrentStableList[SysReleaseManifestDomain]: 明细行。
        """
        statement = (
            self._select().where(self._column("manifest_id") == manifest_id).order_by(self._column("domain_key").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def append_entries(self, manifest_id: int, rows: Iterable[SysReleaseManifestDomain]) -> int:
        """批量追加明细（主表已落库后调用，同事务）。

        Args:
            manifest_id: 清单主键（调用方已回填到每行）。
            rows: 明细行。

        Returns:
            int: 写入条数。
        """
        count = 0
        for row in rows:
            self._session.add(row)
            count += 1
        if count:
            await self._session.flush()
        return count
