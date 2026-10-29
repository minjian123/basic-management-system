"""角色授权读面服务（`RoleGrantPort` 实现）：权限解析所需的三类读，统一回 DTO。"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_platform.domains.role.dto import RoleDataScopeEntry, RolePermissionEntry
from bms_platform.domains.role.repositories.role import (
    DataScopeRepository,
    RolePermissionRepository,
    RoleRepository,
)

__all__ = ["RoleGrantReader"]


class RoleGrantReader(BaseFrameworkObject):
    """角色授权读面：授权条目 / 数据范围 / 角色类型映射。"""

    def __init__(self, session: DbSession) -> None:
        """初始化。

        Args:
            session: 租户库会话。
        """
        self._roles = RoleRepository(session)
        self._permissions = RolePermissionRepository(session)
        self._data_scopes = DataScopeRepository(session)

    async def list_role_types(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableDict[int, str]:
        """取角色主键 → 角色类型映射。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableDict[int, str]: 主键到类型的映射（仅命中项）。
        """
        rows = await self._roles.list_by_ids(ConcurrentStableSet(role_ids))
        return ConcurrentStableDict({row.id: row.role_type for row in rows})

    async def list_permission_grants(
        self, role_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[RolePermissionEntry]:
        """按角色批量取授权条目。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RolePermissionEntry]: 授权条目列表。
        """
        rows = await self._permissions.list_by_roles(ConcurrentStableSet(role_ids))
        return ConcurrentStableList(RolePermissionEntry.from_model(row) for row in rows)

    async def list_data_scopes(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleDataScopeEntry]:
        """按角色批量取数据权限条目。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RoleDataScopeEntry]: 数据权限条目列表。
        """
        rows = await self._data_scopes.list_by_roles(ConcurrentStableSet(role_ids))
        return ConcurrentStableList(RoleDataScopeEntry.from_model(row) for row in rows)
