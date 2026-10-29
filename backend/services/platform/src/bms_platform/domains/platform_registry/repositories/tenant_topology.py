"""租户部署拓扑仓储（平台服务自有）：`sys_tenant_topology` 读写（07C `02_01`）。

- 归属：`sys_tenant_topology` 归 `platform` 服务 × 平台服务库（`bms_platform`），表结构以表文件为准；
- 会话经构造注入；仓储只 `flush` 不 `commit`（事务边界归服务层）；
- **整批替换**：软删除该租户当前行 → 写入新版本行，保证解析永远看到完整版本；
- 版本口径：同一租户的当前版本 = 未软删除行中的最大 `topology_version`。
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, select, update

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.tenant_topology import SysTenantTopology
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery

__all__ = ["TenantTopologyRepository"]


class TenantTopologyRepository(BaseDbRepository[SysTenantTopology]):
    """租户部署拓扑仓储（读写；事务边界归服务层）。"""

    model = SysTenantTopology
    sortable_fields = ConcurrentStableSet({"id", "tenant_id", "domain_key", "unit_key", "topology_version", "status"})

    def _conditions(
        self,
        *,
        tenant_id: int | None = None,
        domain_key: str | None = None,
        unit_key: str | None = None,
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """构造筛选条件（分页用；软删除口径由 `_scope_where` 负责）。

        Args:
            tenant_id: 租户主键筛选；None 不过滤。
            domain_key: 业务域筛选；None 不过滤。
            unit_key: 部署单元筛选；None 不过滤。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if tenant_id is not None:
            conditions.add(self._column("tenant_id") == tenant_id)
        if domain_key is not None:
            conditions.add(self._column("domain_key") == domain_key)
        if unit_key is not None:
            conditions.add(self._column("unit_key") == unit_key)
        return conditions

    async def page_rows(
        self,
        query: BasePageQuery,
        *,
        tenant_id: int | None = None,
        domain_key: str | None = None,
        unit_key: str | None = None,
    ) -> tuple[ConcurrentStableList[SysTenantTopology], int]:
        """分页查询当前版本行（筛选 + 排序 + 当前页 + 筛选后总数）。

        Args:
            query: 页码分页请求（排序经白名单校验、非法忽略）。
            tenant_id: 租户主键筛选。
            domain_key: 业务域筛选。
            unit_key: 部署单元筛选。

        Returns:
            tuple[ConcurrentStableList[SysTenantTopology], int]: (当前页记录, 筛选后总数)。
        """
        conditions = self._conditions(tenant_id=tenant_id, domain_key=domain_key, unit_key=unit_key)
        scope = self._scope_where(include_soft_delete=True)
        selectable = self._select(include_soft_delete=True).where(*conditions)
        statement = self._apply_sort(selectable, self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        count_statement = select(func.count()).select_from(self.model).where(*scope, *conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def current_version(self, tenant_id: int) -> int:
        """取某租户当前版本号（未软删除行的最大 `topology_version`）。

        Args:
            tenant_id: 租户主键（`0` 为默认拓扑）。

        Returns:
            int: 当前版本；无记录返回 0。
        """
        statement = select(func.max(self._column("topology_version"))).where(
            *self._scope_where(include_soft_delete=True),
            self._column("tenant_id") == tenant_id,
        )
        return int((await self._session.execute(statement)).scalar_one() or 0)

    async def list_current(self, tenant_id: int) -> ConcurrentStableList[SysTenantTopology]:
        """取某租户当前版本的全部行（按域升序）。

        Args:
            tenant_id: 租户主键。

        Returns:
            ConcurrentStableList[SysTenantTopology]: 当前版本行。
        """
        version = await self.current_version(tenant_id)
        if version == 0:
            return ConcurrentStableList()
        statement = (
            self._select(include_soft_delete=True)
            .where(
                self._column("tenant_id") == tenant_id,
                self._column("topology_version") == version,
            )
            .order_by(self._column("domain_key").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_current_all(self) -> ConcurrentStableList[SysTenantTopology]:
        """取全部租户当前版本的未软删行（启动装载快照用；行量级为「租户数 × 域数」）。

        Returns:
            ConcurrentStableList[SysTenantTopology]: 当前版本行（按租户 / 域升序）。
        """
        statement = self._select(include_soft_delete=True).order_by(
            self._column("tenant_id").asc(), self._column("domain_key").asc()
        )
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        latest: ConcurrentStableDict[int, int] = ConcurrentStableDict()
        for row in rows:
            if row.topology_version > latest.get(row.tenant_id, 0):
                latest[row.tenant_id] = row.topology_version
        return ConcurrentStableList(row for row in rows if row.topology_version == latest[row.tenant_id])

    async def replace(
        self,
        tenant_id: int,
        *,
        version: int,
        rows: Iterable[SysTenantTopology],
        now: datetime | None = None,
    ) -> int:
        """整批替换某租户的拓扑（软删旧行 + 写入新版本行）。

        Args:
            tenant_id: 租户主键。
            version: 新版本号（由服务层校验递增）。
            rows: 新版本行（已绑定租户与版本）。
            now: 软删除时刻（缺省取当前 UTC；同批次一致）。

        Returns:
            int: 写入行数。
        """
        moment = now or datetime.now(UTC)
        await self._session.execute(
            update(self.model)
            .where(
                *self._scope_where(include_soft_delete=True),
                self._column("tenant_id") == tenant_id,
            )
            .values(deleted_at=moment, updated_at=moment)
        )
        items = ConcurrentStableList(rows)
        for row in items:
            self._session.add(row)
        await self._session.flush()
        return len(items)
