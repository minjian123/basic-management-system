"""组织主数据服务 repositories 层：用户最小模型仓储（`sys_user`）。"""

from datetime import datetime

from sqlalchemy import and_, func, or_

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_org.models.user import SysUser


class UserRepository(BaseDbRepository[SysUser]):
    """用户仓储（`sys_user`）：按账号 / 主键取数 + 基类 CRUD（作用域含软删除）。"""

    model = SysUser
    sortable_fields = ConcurrentStableSet({"id", "username"})

    async def get_by_id(self, user_id: int) -> SysUser | None:
        """按主键查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            user_id: 用户主键。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        return await self.get(user_id)

    async def get_by_username(self, username: str) -> SysUser | None:
        """按登录账号查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            username: 登录账号。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        statement = self._select().where(self._column("username") == username)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> SysUser | None:
        """按邮箱查询单条记录（小写不敏感；多命中取最早一条）。

        Args:
            email: 邮箱地址。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        statement = (
            self._select()
            .where(func.lower(self._column("email")) == email.lower())
            .order_by(self._column("id").asc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def get_by_phone(self, phone: str) -> SysUser | None:
        """按手机号查询单条记录（精确匹配；多命中取最早一条）。

        Args:
            phone: 手机号。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        statement = self._select().where(self._column("phone") == phone).order_by(self._column("id").asc()).limit(1)
        return (await self._session.execute(statement)).scalars().first()

    async def list_inactive(self, threshold: datetime, *, now: datetime) -> ConcurrentStableList[SysUser]:
        """列出不活跃待锁定候选：启用、未锁定、最近登录（或建号）早于阈值。

        - 未软删除、`status = enabled`、`locked_until` 为 NULL 或已到期；
        - `last_login_at` 非空且早于阈值，或 `last_login_at` 为空（从未登录）且 `created_at` 早于阈值。

        Args:
            threshold: 不活跃阈值时间（UTC naive）。
            now: 当前时间（UTC naive；判定锁定是否仍生效）。

        Returns:
            ConcurrentStableList[SysUser]: 候选用户列表。
        """
        never_logged_in = and_(
            self._column("last_login_at").is_(None),
            self._column("created_at") < threshold,
        )
        stale_login = and_(
            self._column("last_login_at").is_not(None),
            self._column("last_login_at") < threshold,
        )
        statement = self._select().where(
            self._column("deleted_at").is_(None),
            self._column("status") == "enabled",
            or_(self._column("locked_until").is_(None), self._column("locked_until") <= now),
            or_(never_logged_in, stale_login),
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())
