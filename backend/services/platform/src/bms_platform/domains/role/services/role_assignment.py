"""用户 × 角色分配服务（`RoleAssignmentPort` 实现）：`sys_user_role` 的写只在本域执行。

改造前由用户域借角色仓储直接写「软删 + 恢复 + 新建」三段，D4「跨域写无例外」靠评审守；
现收敛为一个语义接口 `set_user_roles`，事务边界仍由调用方传入的 `uow` 决定（同一事务）。
"""

from __future__ import annotations

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import RoleNotFoundError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.session import DbSession
from bms_core.models.platform.role import SysRole
from bms_platform.domains.role.dto import RoleSummary
from bms_platform.domains.role.ports import SeparationPort
from bms_platform.domains.role.repositories.role import RoleRepository, UserRoleRepository

__all__ = ["RoleAssignmentService"]


def dedupe(values: ConcurrentStableList[int]) -> ConcurrentStableList[int]:
    """入参去重（保持首次出现序）。

    Args:
        values: 原始主键清单。

    Returns:
        ConcurrentStableList[int]: 去重后的清单。
    """
    seen: ConcurrentStableSet[int] = ConcurrentStableSet()
    result: ConcurrentStableList[int] = ConcurrentStableList()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.add(value)
    return result


class RoleAssignmentService(BaseFrameworkObject):
    """用户 × 角色分配：读绑定与「全量覆盖」写。"""

    def __init__(self, session: DbSession, *, guard: SeparationPort | None = None) -> None:
        """初始化。

        Args:
            session: 租户库会话。
            guard: 三权分立校验器（None 时不做互斥校验，仅全局事务分支如此）。
        """
        self._roles = RoleRepository(session)
        self._user_roles = UserRoleRepository(session)
        self._guard = guard

    async def list_role_ids_of_user(self, user_id: int) -> ConcurrentStableList[int]:
        """取用户持有的角色主键（按主键升序）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[int]: 角色主键列表。
        """
        return await self._user_roles.list_role_ids_by_user(user_id)

    async def count_by_user(self, user_id: int) -> int:
        """统计用户在角色分配上的行数。

        Args:
            user_id: 用户主键。

        Returns:
            int: 分配行数。
        """
        return await self._user_roles.count_by_user(user_id)

    async def list_roles_of_user(self, user_id: int) -> ConcurrentStableList[RoleSummary]:
        """取用户持有的角色绑定。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[RoleSummary]: 角色绑定列表。
        """
        role_ids = await self._user_roles.list_role_ids_by_user(user_id)
        if not role_ids:
            return ConcurrentStableList()
        rows = await self._roles.list_by_ids(ConcurrentStableSet(role_ids))
        return ConcurrentStableList(RoleSummary.from_model(row) for row in rows)

    async def set_user_roles(
        self, user_id: int, role_ids: ConcurrentStableList[int]
    ) -> ConcurrentStableList[RoleSummary]:
        """全量覆盖用户角色（集合外软删、集合内恢复或新建）。

        Args:
            user_id: 用户主键。
            role_ids: 目标角色主键集合（全量）。

        Returns:
            ConcurrentStableList[RoleSummary]: 生效后的角色绑定（与入参去重后同序）。

        Raises:
            RoleNotFoundError: 角色不存在。
            UserSeparationConflictError: 目标角色集合含两类内置管理员（30010）。
        """
        normalized = dedupe(role_ids)
        selected: ConcurrentStableList[SysRole] = ConcurrentStableList()
        for role_id in normalized:
            row = await self._roles.get(role_id)
            if row is None:
                raise RoleNotFoundError(f"角色不存在：{role_id}")
            selected.add(row)
        if self._guard is not None and normalized:
            await self._guard.ensure_user_roles_exclusive(
                user_ids=ConcurrentStableList([user_id]),
                roles=ConcurrentStableList(RoleSummary.from_model(row) for row in selected),
            )
        await self._user_roles.soft_delete_by_user_except(user_id, ConcurrentStableSet(normalized))
        for role_id in normalized:
            if await self._user_roles.get_by_role_user(role_id, user_id) is not None:
                continue
            deleted = await self._user_roles.get_deleted_by_role_user(role_id, user_id)
            if deleted is not None:
                await self._user_roles.restore(deleted.id)
            else:
                await self._user_roles.create(role_id=role_id, user_id=user_id)
        return ConcurrentStableList(RoleSummary.from_model(row) for row in selected)
