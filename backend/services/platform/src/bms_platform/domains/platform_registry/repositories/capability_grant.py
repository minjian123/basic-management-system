"""能力分配授权仓储（平台服务自有）：`sys_capability_grant` 读写（07B `02_04`）。

- 归属：`sys_capability_grant` 归 `platform` 服务 × 平台服务库（`bms_platform`），表结构以表文件为准；
- 会话经构造注入（请求级会话 / 启动钩子的 `session_scope`）；仓储只 `flush` 不 `commit`；
- 读侧三个方向：管理面分页、授权视图（provider / consumer 两维度）、声明同步的全量现状；
- 撤销是**软撤销**（`status` + `revoked_at`），不删行。
"""

from sqlalchemy import ColumnElement, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.models.platform.capability_grant import (
    GRANT_STATUS_ENABLED,
    SysCapabilityGrant,
)
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery


class CapabilityGrantRepository(BaseDbRepository[SysCapabilityGrant]):
    """能力分配授权仓储（读写；事务边界归服务层）。"""

    model = SysCapabilityGrant
    sortable_fields = ConcurrentStableSet({"id", "capability_name", "consumer_key", "status", "source", "granted_at"})

    async def flush(self) -> None:
        """落库当前会话变更（服务层在同一事务内直接改 ORM 属性后调用）。"""
        await self._session.flush()

    def _conditions(
        self,
        *,
        capability: str | None = None,
        consumer: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """构造筛选条件（分页与视图查询同源）。

        Args:
            capability: 能力名筛选；None 不过滤。
            consumer: 消费方标识筛选；None 不过滤。
            status: 状态筛选；None 不过滤。
            source: 来源筛选；None 不过滤。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if capability is not None:
            conditions.add(self._column("capability_name") == capability)
        if consumer is not None:
            conditions.add(self._column("consumer_key") == consumer)
        if status is not None:
            conditions.add(self._column("status") == status)
        if source is not None:
            conditions.add(self._column("source") == source)
        return conditions

    async def page_grants(
        self,
        query: BasePageQuery,
        *,
        capability: str | None = None,
        consumer: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> tuple[ConcurrentStableList[SysCapabilityGrant], int]:
        """分页查询授权记录（筛选 + 排序 + 当前页 + 筛选后总数）。

        Args:
            query: 页码分页请求（排序经白名单校验、非法忽略）。
            capability: 能力名筛选。
            consumer: 消费方标识筛选。
            status: 状态筛选。
            source: 来源筛选。

        Returns:
            tuple[ConcurrentStableList[SysCapabilityGrant], int]: (当前页记录, 筛选后总数)。
        """
        conditions = self._conditions(capability=capability, consumer=consumer, status=status, source=source)
        statement = self._apply_sort(self._select().where(*conditions), self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        count_statement = select(func.count()).select_from(self.model).where(*self._scope_where(), *conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def get_by_pair(self, capability: str, consumer: str) -> SysCapabilityGrant | None:
        """按 `(能力, 消费方)` 取未软删记录。

        Args:
            capability: 能力名。
            consumer: 消费方标识。

        Returns:
            SysCapabilityGrant | None: 记录；不存在返回 None。
        """
        statement = self._select().where(
            self._column("capability_name") == capability,
            self._column("consumer_key") == consumer,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> ConcurrentStableList[SysCapabilityGrant]:
        """取全部未软删记录（声明同步的现状基线，`id` 升序）。

        Returns:
            ConcurrentStableList[SysCapabilityGrant]: 记录列表。
        """
        statement = self._select().order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_enabled_by_consumer(self, consumer: str) -> ConcurrentStableList[SysCapabilityGrant]:
        """取某消费方的启用记录（出站视图 / 出站 scope 派生）。

        Args:
            consumer: 消费方标识（服务键）。

        Returns:
            ConcurrentStableList[SysCapabilityGrant]: 记录列表。
        """
        statement = (
            self._select()
            .where(
                self._column("consumer_key") == consumer,
                self._column("status") == GRANT_STATUS_ENABLED,
            )
            .order_by(self._column("id").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_enabled_by_capabilities(
        self, capabilities: ConcurrentStableList[str]
    ) -> ConcurrentStableList[SysCapabilityGrant]:
        """取若干能力的启用记录（入站视图：某提供方业务域下的能力）。

        Args:
            capabilities: 能力名清单（空清单返回空结果）。

        Returns:
            ConcurrentStableList[SysCapabilityGrant]: 记录列表。
        """
        if not capabilities:
            return ConcurrentStableList()
        statement = (
            self._select()
            .where(
                self._column("capability_name").in_(list(capabilities)),
                self._column("status") == GRANT_STATUS_ENABLED,
            )
            .order_by(self._column("id").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())
