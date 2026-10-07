"""平台服务 services 层：角色分配服务（角色 × 用户分配：已分配列表 / 批量分配 / 解绑）。

口径（需求 07-3、《概要设计 · 角色管理》）：

- 分配表 `sys_user_role` 与用户表 `sys_user` **同库**（platform 服务租户库 `bms_platform_{code}`）
  → 用户有效性校验与已分配列表**同库完成**（子查询过滤，不跨服务）；
- **批量分配幂等 upsert**：已生效行跳过；仅存历史软删行则**恢复原行**（清 `deleted_at`），
  保证「同角色同用户」始终只有一行有效记录；其余新建；
- 分配主体（用户）不存在 / 已停用 → `30045`（`RoleSubjectInvalidError`）；
- 解绑为**软删除**；分配 / 解绑变更成功即**一次**权限版本 +1（`bms:{租户}:permission:version`）；
- 岗位 / 部门分配归 mdm 组织域（经只读契约核验，mdm 未就绪期间按降级跳过），本服务不涉。
"""

from __future__ import annotations

from bms_core.cache.base import CacheRegion
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.exceptions import RoleNotFoundError, RoleSubjectInvalidError
from bms_core.core.objects import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.permission.version import permission_version_key
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.user import SysUser
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository

ENABLED_USER_STATUS = "enabled"
"""可分配用户状态（停用用户不可分配）。"""


class RoleAssignService(BaseFrameworkObject):
    """角色分配服务：角色 × 用户分配的读取、批量分配（幂等 upsert）与解绑。"""

    def __init__(
        self,
        roles: RoleRepository,
        user_roles: UserRoleRepository,
        users: UserRepository,
        uow: UnitOfWork,
        cache: CacheRegion,
    ) -> None:
        """初始化。

        Args:
            roles: 角色仓储。
            user_roles: 角色 × 用户分配仓储（`sys_user_role`）。
            users: 用户仓储（`sys_user`，同库）。
            uow: 工作单元（platform 服务租户库写事务边界）。
            cache: 缓存能力域（分配变更后权限版本 +1）。
        """
        self._roles = roles
        self._user_roles = user_roles
        self._users = users
        self._uow = uow
        self._cache = cache

    async def list_assigned(
        self,
        role_id: int,
        query: BasePageQuery,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysUser], int]:
        """分页查询角色已分配用户（关键字 / 状态筛选，同库取用户属性）。

        Args:
            role_id: 角色主键。
            query: 页码分页请求。
            keyword: 关键字（用户账号 / 姓名）。
            status: 用户状态。

        Returns:
            tuple[ConcurrentStableList[SysUser], int]: 当前页用户与总条数。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        await self._require_role(role_id)
        rows = await self._user_roles.list_filtered_by_role(role_id, query, keyword=keyword, status=status)
        total = await self._user_roles.count_filtered_by_role(role_id, keyword=keyword, status=status)
        users = await self._users.list_by_ids(ConcurrentStableList(row.user_id for row in rows))
        by_id = ConcurrentStableDict[int, SysUser]({user.id: user for user in users})
        return ConcurrentStableList(by_id[row.user_id] for row in rows if row.user_id in by_id), total

    async def assign_users(
        self,
        role_id: int,
        user_ids: ConcurrentStableList[int],
        *,
        tenant_id: str | None,
    ) -> ConcurrentStableList[SysUser]:
        """批量分配用户（幂等 upsert：已分配跳过、历史软删行恢复、其余新建）。

        Args:
            role_id: 角色主键。
            user_ids: 用户主键清单（重复项自动去重、保持首次出现序）。
            tenant_id: 租户标识（权限版本键作用域）。

        Returns:
            ConcurrentStableList[SysUser]: 分配后的用户清单（与入参去重后同序）。

        Raises:
            RoleNotFoundError: 角色不存在。
            RoleSubjectInvalidError: 存在不存在 / 已停用的用户（30045）。
        """
        normalized = self._dedupe(user_ids)
        if not normalized:
            return ConcurrentStableList()
        changed = False
        async with self._uow.begin():
            await self._require_role(role_id)
            users = await self._users.list_by_ids(normalized)
            by_id = ConcurrentStableDict[int, SysUser]({user.id: user for user in users})
            invalid = ConcurrentStableList(
                user_id
                for user_id in normalized
                if user_id not in by_id or by_id[user_id].status != ENABLED_USER_STATUS
            )
            if invalid:
                raise RoleSubjectInvalidError(f"用户不存在或已停用：{tuple(invalid)}")
            for user_id in normalized:
                if await self._user_roles.get_by_role_user(role_id, user_id) is not None:
                    continue
                deleted = await self._user_roles.get_deleted_by_role_user(role_id, user_id)
                if deleted is not None:
                    await self._user_roles.restore(deleted.id)
                else:
                    await self._user_roles.create(role_id=role_id, user_id=user_id)
                changed = True
        if changed:
            await self._bump_version(tenant_id)
        return ConcurrentStableList(by_id[user_id] for user_id in normalized)

    async def unassign_user(self, role_id: int, user_id: int, *, tenant_id: str | None) -> bool:
        """解绑用户（软删分配行；未分配时幂等无操作）。

        Args:
            role_id: 角色主键。
            user_id: 用户主键。
            tenant_id: 租户标识（权限版本键作用域）。

        Returns:
            bool: 命中并解绑 True；该用户本就未分配 False。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        async with self._uow.begin():
            await self._require_role(role_id)
            removed = await self._user_roles.soft_delete_by_role_user(role_id, user_id)
        if removed:
            await self._bump_version(tenant_id)
        return removed

    @staticmethod
    def _dedupe(user_ids: ConcurrentStableList[int]) -> ConcurrentStableList[int]:
        """入参去重（保持首次出现序）。

        Args:
            user_ids: 原始用户主键清单。

        Returns:
            ConcurrentStableList[int]: 去重后的用户主键清单。
        """
        seen: ConcurrentStableSet[int] = ConcurrentStableSet()
        result: ConcurrentStableList[int] = ConcurrentStableList()
        for user_id in user_ids:
            if user_id in seen:
                continue
            seen.add(user_id)
            result.add(user_id)
        return result

    async def _bump_version(self, tenant_id: str | None) -> None:
        """权限版本 +1（分配变更后一次递增，供权限计算失效）。

        Args:
            tenant_id: 租户标识。
        """
        await self._cache.aincrease(permission_version_key(tenant_id))

    async def _require_role(self, role_id: int) -> None:
        """校验角色存在。

        Args:
            role_id: 角色主键。

        Raises:
            RoleNotFoundError: 角色不存在。
        """
        if await self._roles.get(role_id) is None:
            raise RoleNotFoundError()
