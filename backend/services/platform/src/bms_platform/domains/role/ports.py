"""角色业务域领域服务接口（Protocol）：跨域消费方只依赖本模块的协议。

实现类留在域内（`services/`），由装配面 `bms_platform.wiring` 构造后注入；出口因此只暴露
**契约**——加实现类方法不会静默扩出口面，改协议必须动本文件。
"""

from __future__ import annotations

from typing import Protocol

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_platform.domains.role.dto import (
    RoleDataScopeEntry,
    RoleDetailSnapshot,
    RolePermissionEntry,
    RoleSummary,
)

__all__ = [
    "RoleAssignmentPort",
    "RoleGrantPort",
    "RoleQueryPort",
    "RoleReferencePort",
    "SeparationPort",
]


class RoleQueryPort(Protocol):
    """角色读面：单条 / 批量 / 按码。"""

    async def get(self, role_id: int) -> RoleDetailSnapshot | None:
        """取角色详情。

        Args:
            role_id: 角色主键。

        Returns:
            RoleDetailSnapshot | None: 角色详情；不存在返回 None。
        """
        ...

    async def list_by_ids(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleSummary]:
        """按主键批量取角色引用（未命中项跳过，保序）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色引用列表。
        """
        ...

    async def list_by_code(self, code: str) -> RoleSummary | None:
        """按角色码取引用。

        Args:
            code: 角色码。

        Returns:
            RoleSummary | None: 角色引用；不存在返回 None。
        """
        ...


class RoleAssignmentPort(Protocol):
    """用户 × 角色分配：读绑定与「全量覆盖」写。"""

    async def list_role_ids_of_user(self, user_id: int) -> ConcurrentStableList[int]:
        """取用户持有的角色主键（按主键升序）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[int]: 角色主键列表。
        """
        ...

    async def count_by_user(self, user_id: int) -> int:
        """统计用户在角色分配上的行数（删除前置校验用）。

        Args:
            user_id: 用户主键。

        Returns:
            int: 分配行数。
        """
        ...

    async def list_roles_of_user(self, user_id: int) -> ConcurrentStableList[RoleSummary]:
        """取用户持有的角色绑定（角色引用形态）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色绑定列表。
        """
        ...

    async def set_user_roles(
        self, user_id: int, role_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[RoleSummary]:
        """全量覆盖用户角色：集合外软删、集合内恢复或新建（写回角色域执行）。

        Args:
            user_id: 用户主键。
            role_ids: 目标角色主键集合（全量）。

        Returns:
            ConcurrentStableList[RoleSummary]: 生效后的角色绑定（与入参去重后同序）。

        Raises:
            RoleNotFoundError: 角色不存在。
            UserSeparationConflictError: 目标角色集合含两类内置管理员。
        """
        ...


class RoleGrantPort(Protocol):
    """角色授权读面：授权条目 / 字段权限 / 数据范围 / 角色类型映射。"""

    async def list_role_types(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableDict[int, str]:
        """取角色主键 → 角色类型映射（仅命中项）。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableDict[int, str]: 主键到类型的映射。
        """
        ...

    async def list_permission_grants(
        self, role_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[RolePermissionEntry]:
        """按角色批量取授权条目。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RolePermissionEntry]: 授权条目列表。
        """
        ...

    async def list_data_scopes(self, role_ids: ConcurrentStableList[int]) -> ConcurrentStableList[RoleDataScopeEntry]:
        """按角色批量取数据权限条目。

        Args:
            role_ids: 角色主键集合。

        Returns:
            ConcurrentStableList[RoleDataScopeEntry]: 数据权限条目列表。
        """
        ...


class RoleReferencePort(Protocol):
    """角色引用面：字典数据源需要的启用角色清单。"""

    async def list_options(self) -> ConcurrentStableList[RoleSummary]:
        """取启用状态的角色（按主键升序，供字典数据源渲染）。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色摘要列表。
        """
        ...


class SeparationPort(Protocol):
    """三权分立校验面：目标角色集合互斥（内置管理员不得并存）。"""

    async def ensure_user_roles_exclusive(
        self, *, user_ids: ConcurrentStableList[int], roles: ConcurrentStableList[RoleSummary]
    ) -> None:
        """校验目标角色集合不含两类内置管理员。

        Args:
            user_ids: 涉及的用户主键（审计与提示用）。
            roles: 目标角色（摘要形态）。

        Raises:
            UserSeparationConflictError: 集合同时含系统管理员与审计管理员（30010）。
        """
        ...
