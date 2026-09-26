"""组织主数据服务 repositories 层：用户最小模型仓储（`sys_user`）。"""

from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_org.models.user import SysUser


class UserRepository(BaseDbRepository[SysUser]):
    """用户仓储（`sys_user`）：按账号取数 + 基类 CRUD（作用域含软删除）。"""

    model = SysUser
    sortable_fields = frozenset({"id", "username"})

    async def get_by_username(self, username: str) -> SysUser | None:
        """按登录账号查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            username: 登录账号。

        Returns:
            SysUser | None: 用户记录；不存在返回 None。
        """
        statement = self._select().where(self._column("username") == username)
        return (await self._session.execute(statement)).scalar_one_or_none()
