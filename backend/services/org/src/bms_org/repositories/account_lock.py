"""组织主数据服务 repositories 层：账号锁定记录仓储（`sys_account_lock`）。"""

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_org.models.account_lock import SysAccountLock


class AccountLockRepository(BaseDbRepository[SysAccountLock]):
    """账号锁定记录仓储（`sys_account_lock`）：按用户取活跃锁 + 基类 CRUD。"""

    model = SysAccountLock
    sortable_fields = frozenset({"id", "locked_at"})

    async def get_active_by_user(self, user_id: int) -> SysAccountLock | None:
        """取用户当前未解锁的锁定记录（`unlock_at IS NULL`；多条取最近一条）。

        Args:
            user_id: 用户主键。

        Returns:
            SysAccountLock | None: 活跃锁记录；无则 None。
        """
        statement = (
            self._select()
            .where(self._column("user_id") == user_id, self._column("unlock_at").is_(None))
            .order_by(self._column("locked_at").desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()
