"""角色读面服务（`RoleQueryPort` 实现）：出口只回 DTO，不回 ORM 模型。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_platform.domains.role.dto import RoleDetailSnapshot, RoleSummary
from bms_platform.domains.role.repositories.role import RoleRepository

__all__ = ["RoleQueryService"]


class RoleQueryService(BaseFrameworkObject):
    """角色读面：单条 / 批量 / 按码。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._roles = RoleRepository(session)

    async def get(self, role_id: int) -> RoleDetailSnapshot | None:
        """取角色详情。

        Args:
            role_id: 角色主键。

        Returns:
            RoleDetailSnapshot | None: 角色详情；不存在返回 None。
        """
        row = await self._roles.get(role_id)
        return None if row is None else RoleDetailSnapshot.from_model(row)

    async def list_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleSummary]:
        """按主键批量取角色引用（未命中项跳过，保序）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色引用列表。
        """
        rows = await self._roles.list_by_ids(ConcurrentStableSet(role_ids))
        return ConcurrentStableList(RoleSummary.from_model(row) for row in rows)

    async def list_by_code(self, code: str) -> RoleSummary | None:
        """按角色码取引用。

        Args:
            code: 角色码。

        Returns:
            RoleSummary | None: 角色引用；不存在返回 None。
        """
        row = await self._roles.get_by_code(code)
        return None if row is None else RoleSummary.from_model(row)
