"""租户部署拓扑仓储（平台服务自有）：`sys_tenant_topology` 读写（07C `02_01`）。

- 归属：`sys_tenant_topology` 归 `platform` 服务 × 平台服务库（`bms_platform`），表结构以表文件为准；
- 会话经构造注入；仓储只 `flush` 不 `commit`（事务边界归服务层）；
- **整批替换**：软删除该租户当前行 → 写入新版本行，保证解析永远看到完整版本；
- 版本口径：同一租户的当前版本 = 未软删除行中的最大 `topology_version`。
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, func, select

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
            # 原子写绕过 ORM 身份映射：读回一律按库内真值覆盖已加载实例
            .execution_options(populate_existing=True)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_current_all(self) -> ConcurrentStableList[SysTenantTopology]:
        """取全部租户当前版本的未软删行（启动装载快照用；行量级为「租户数 × 域数」）。

        Returns:
            ConcurrentStableList[SysTenantTopology]: 当前版本行（按租户 / 域升序）。
        """
        statement = (
            self._select(include_soft_delete=True)
            .order_by(self._column("tenant_id").asc(), self._column("domain_key").asc())
            .execution_options(populate_existing=True)
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
        """整批替换某租户的拓扑（先原子写新版本行，再原子软删旧版本）。

        为什么用原语而不是 ORM：`ensure_default` 在多个 worker 启动时并发执行，两边会算出同一个
        下一版本。ORM 的「先软删、后多行插入」会让后写方插出同域重复行，随后软删撞
        `(tenant_id, domain_key, deleted_at)` 唯一键。改为「逐行 `INSERT ... WHERE NOT EXISTS`
        （按业务键 + 版本判重）+ 按版本条件批量软删」后，并发的两方收敛到同一版本。

        顺序是**先插后删**：任何时刻读方按「最大版本」取行，都不会看到空拓扑。

        Args:
            tenant_id: 租户主键。
            version: 新版本号（由服务层校验递增）。
            rows: 新版本行（只用 `domain_key` / `unit_key` / `status` / `note` 四个字段；
                租户与版本由本方法统一写入，避免两份事实源）。
            now: 软删除时刻（缺省取当前 UTC；同批次一致）。

        Returns:
            int: 实际插入行数（并发时部分行可能已由其它写者插入，按实际插入计数）。
        """
        items = ConcurrentStableList(rows)
        written = 0
        for row in items:
            payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(
                {
                    "domain_key": row.domain_key,
                    "unit_key": row.unit_key,
                    "status": row.status,
                    "note": row.note,
                    "tenant_id": tenant_id,
                    "topology_version": version,
                }
            )
            inserted = await self.insert_if_absent(
                payload,
                match=self.version_match(tenant_id, row.domain_key, version),
            )
            written += 1 if inserted else 0
        await self.soft_delete_below(tenant_id, version, now=now or datetime.now(UTC))
        return written

    async def soft_delete_below(self, tenant_id: int, version: int, *, now: datetime) -> int:
        """软删该租户版本号小于 `version` 的未删行（**逐行、时刻递增**）。

        为什么不能一条 `UPDATE ... WHERE topology_version < :version`：唯一键是
        `(tenant_id, domain_key, deleted_at)`，而同域可能同时存在多个旧版本行（并发替换乱序完成时：
        v8 先落、v7 后落），一条语句会把同域的多行写成同一个 `deleted_at`，直接撞唯一键。
        逐行写且每行 `now` 递增 1 微秒，既保留「本批删除」的语义，也保证跨方言都不会撞键。

        Args:
            tenant_id: 租户主键。
            version: 新版本号（删除严格小于它的行）。
            now: 本批软删基准时刻。

        Returns:
            int: 实际软删行数。
        """
        statement = select(self._column("id")).where(
            *self._scope_where(),
            self._column("tenant_id") == tenant_id,
            self._column("topology_version") < version,
        )
        ids = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        deleted = 0
        for index, row_id in enumerate(ids):
            deleted += await self.soft_delete_where(
                ConcurrentStableList((self._column("id") == row_id,)),
                now=now + timedelta(microseconds=index + 1),
            )
        return deleted

    def version_match(self, tenant_id: int, domain_key: str, version: int) -> ConcurrentStableList[ColumnElement[bool]]:
        """按「租户 + 业务域 + 版本」构造原子写定位条件。

        Args:
            tenant_id: 租户主键。
            domain_key: 业务域标识。
            version: 拓扑版本号。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 定位条件（未删过滤由基座方法追加）。
        """
        return ConcurrentStableList(
            (
                self._column("tenant_id") == tenant_id,
                self._column("domain_key") == domain_key,
                self._column("topology_version") == version,
            )
        )
