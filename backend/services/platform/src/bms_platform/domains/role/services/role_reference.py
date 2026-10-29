"""角色引用服务（`RoleReferencePort` 实现）：字典数据源用的启用角色清单。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_platform.domains.role.dto import RoleSummary
from bms_platform.domains.role.repositories.role import RoleRepository

__all__ = ["RoleReferenceService"]


class RoleReferenceService(BaseFrameworkObject):
    """角色引用面（只读）。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._roles = RoleRepository(session)

    async def list_options(self) -> ConcurrentStableList[RoleSummary]:
        """取启用状态的角色（按主键升序）。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色摘要列表。
        """
        rows = await self._roles.list_enabled()
        return ConcurrentStableList(RoleSummary.from_model(row) for row in rows)
