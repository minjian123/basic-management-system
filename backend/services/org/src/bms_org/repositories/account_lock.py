"""组织主数据服务 repositories 层：账号锁定记录仓储（`sys_account_lock`）。"""

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, and_, func, or_, select

from bms_core.core.concurrent import ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_org.models.account_lock import SysAccountLock


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class AccountLockRepository(BaseDbRepository[SysAccountLock]):
    """账号锁定记录仓储（`sys_account_lock`）：按用户取活跃锁 + 筛选分页 + 基类 CRUD。"""

    model = SysAccountLock
    sortable_fields = ConcurrentStableSet({"id", "locked_at"})

    async def get_active_by_user(self, user_id: int, *, now: datetime | None = None) -> SysAccountLock | None:
        """取用户当前**生效**的锁定记录（`unlock_at IS NULL` 且未到期；多条取最近一条）。

        Args:
            user_id: 用户主键。
            now: 当前时间（UTC naive；判定 `expire_at` 是否已过，None 取当前 UTC）。

        Returns:
            SysAccountLock | None: 生效锁记录；无则 None。
        """
        current = now or _utc_now()
        statement = (
            self._select()
            .where(
                self._column("user_id") == user_id,
                self._column("unlock_at").is_(None),
                or_(self._column("expire_at").is_(None), self._column("expire_at") > current),
            )
            .order_by(self._column("locked_at").desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def get_open_by_user(self, user_id: int, *, lock_type: str | None = None) -> SysAccountLock | None:
        """取用户当前**未解锁**记录（`unlock_at IS NULL`；可含已到期未闭锁行；多条取最近一条）。

        Args:
            user_id: 用户主键。
            lock_type: 锁定类型（可选过滤）。

        Returns:
            SysAccountLock | None: 未解锁记录；无则 None。
        """
        conditions = [self._column("user_id") == user_id, self._column("unlock_at").is_(None)]
        if lock_type is not None:
            conditions.append(self._column("lock_type") == lock_type)
        statement = self._select().where(*conditions).order_by(self._column("locked_at").desc()).limit(1)
        return (await self._session.execute(statement)).scalars().first()

    async def list_filtered(
        self,
        query: BasePageQuery,
        *,
        user_id: int | None = None,
        lock_type: str | None = None,
        active: bool | None = None,
        locked_from: datetime | None = None,
        locked_to: datetime | None = None,
        now: datetime | None = None,
    ) -> list[SysAccountLock]:
        """按筛选条件分页查询锁定记录（页码分页；排序经白名单）。

        Args:
            query: 页码分页请求（含排序参数）。
            user_id: 用户主键（精确）。
            lock_type: 锁定类型（精确）。
            active: 是否生效中（True=未解锁且未到期；False=已解锁或已到期；None=全部）。
            locked_from: 锁定时间下界（UTC，闭区间）。
            locked_to: 锁定时间上界（UTC，闭区间）。
            now: 当前时间（UTC naive；活跃判定用，None 取当前 UTC）。

        Returns:
            list[SysAccountLock]: 当前页记录。
        """
        statement = self._apply_sort(self._select(), self._resolve_sort(query)).where(
            *self._filter_conditions(
                user_id=user_id,
                lock_type=lock_type,
                active=active,
                locked_from=locked_from,
                locked_to=locked_to,
                now=now,
            )
        )
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        *,
        user_id: int | None = None,
        lock_type: str | None = None,
        active: bool | None = None,
        locked_from: datetime | None = None,
        locked_to: datetime | None = None,
        now: datetime | None = None,
    ) -> int:
        """按筛选条件统计锁定记录数（与 `list_filtered` 同口径）。

        Args:
            user_id: 用户主键（精确）。
            lock_type: 锁定类型（精确）。
            active: 是否生效中（True / False / None）。
            locked_from: 锁定时间下界（UTC，闭区间）。
            locked_to: 锁定时间上界（UTC，闭区间）。
            now: 当前时间（UTC naive；活跃判定用，None 取当前 UTC）。

        Returns:
            int: 记录条数。
        """
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(
                *self._scope_where(),
                *self._filter_conditions(
                    user_id=user_id,
                    lock_type=lock_type,
                    active=active,
                    locked_from=locked_from,
                    locked_to=locked_to,
                    now=now,
                ),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    def _filter_conditions(
        self,
        *,
        user_id: int | None,
        lock_type: str | None,
        active: bool | None,
        locked_from: datetime | None,
        locked_to: datetime | None,
        now: datetime | None,
    ) -> list[ColumnElement[bool]]:
        """组装列表 / 统计筛选条件（`active` 以 `unlock_at` 与 `expire_at` 联合判定）。

        Args:
            user_id: 用户主键（精确）。
            lock_type: 锁定类型（精确）。
            active: 是否生效中。
            locked_from: 锁定时间下界。
            locked_to: 锁定时间上界。
            now: 当前时间。

        Returns:
            list[ColumnElement[bool]]: SQL 条件列表。
        """
        conditions: list[ColumnElement[bool]] = []
        if user_id is not None:
            conditions.append(self._column("user_id") == user_id)
        if lock_type is not None:
            conditions.append(self._column("lock_type") == lock_type)
        if active is not None:
            current = now or _utc_now()
            not_expired = or_(
                self._column("expire_at").is_(None),
                self._column("expire_at") > current,
            )
            if active:
                conditions.append(and_(self._column("unlock_at").is_(None), not_expired))
            else:
                conditions.append(
                    or_(
                        self._column("unlock_at").is_not(None),
                        and_(self._column("expire_at").is_not(None), self._column("expire_at") <= current),
                    )
                )
        if locked_from is not None:
            conditions.append(self._column("locked_at") >= locked_from)
        if locked_to is not None:
            conditions.append(self._column("locked_at") <= locked_to)
        return conditions
