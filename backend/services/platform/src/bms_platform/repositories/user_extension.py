"""平台服务 repositories 层：用户扩展信息仓储（`sys_user_extension`）。"""

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_platform.models.system import SysUserExtension


class UserExtensionRepository(BaseDbRepository[SysUserExtension]):
    """用户扩展信息仓储（`sys_user_extension`）：按用户列示 + 同键探测 + 基类 CRUD。"""

    model = SysUserExtension

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SysUserExtension]:
        """按用户列示扩展信息（软删除过滤；主键升序）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysUserExtension]: 扩展信息列表（插入序）。
        """
        statement = self._select().where(self._column("user_id") == user_id).order_by(self._column("id"))
        result = await self._session.execute(statement)
        return ConcurrentStableList(result.scalars().all())

    async def get_by_label(self, user_id: int, label: str) -> SysUserExtension | None:
        """按「用户 + 标签」探测既有行（软删除过滤）。

        Args:
            user_id: 用户主键。
            label: 扩展标签。

        Returns:
            SysUserExtension | None: 既有行；无则 None。
        """
        statement = self._select().where(self._column("user_id") == user_id, self._column("label") == label).limit(1)
        return (await self._session.execute(statement)).scalars().first()
