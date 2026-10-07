"""平台服务 repositories 层：角色域仓储。

覆盖 `sys_role` / `sys_user_role` / `sys_role_permission` / `sys_role_field` / `sys_data_scope` 五表
（platform 服务租户库 `bms_platform_{code}`）；授权全量覆盖提交以「按角色批量软删 + 重建」实现。
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import ColumnElement, func, or_, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.role import SysDataScope, SysRole, SysRoleField, SysRolePermission, SysUserRole


def _utc_now() -> datetime:
    """当前 UTC 时间（naive，跨库统一存储）。

    Returns:
        datetime: UTC 时间。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class RoleRepository(BaseDbRepository[SysRole]):
    """角色仓储（`sys_role`）：按码取数 + 关键字 / 状态筛选分页 + 基类 CRUD。"""

    model = SysRole
    sortable_fields = ConcurrentStableSet({"id", "code", "name", "status"})

    async def flush(self) -> None:
        """落库当前会话变更（服务层在同一事务内直接改 ORM 属性后调用）。"""
        await self._session.flush()

    async def get_by_code(self, code: str) -> SysRole | None:
        """按角色码查询单条记录（软删除后不可见）。

        Args:
            code: 角色码。

        Returns:
            SysRole | None: 角色记录；不存在返回 None。
        """
        statement = self._select().where(self._column("code") == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_filtered(
        self,
        query: BasePageQuery,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> ConcurrentStableList[SysRole]:
        """按筛选条件分页查询角色（页码分页；排序经白名单）。

        Args:
            query: 页码分页请求（含排序参数）。
            keyword: 关键字（匹配角色码 / 名称，大小写不敏感）。
            status: 状态（精确）。

        Returns:
            ConcurrentStableList[SysRole]: 当前页记录。
        """
        statement = (
            self._apply_sort(self._select(), self._resolve_sort(query))
            .where(*self._filter_conditions(keyword=keyword, status=status))
            .limit(query.size)
            .offset((query.page - 1) * query.size)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_filtered(self, *, keyword: str | None = None, status: str | None = None) -> int:
        """按筛选条件统计角色数（与 `list_filtered` 同口径）。

        Args:
            keyword: 关键字（匹配角色码 / 名称）。
            status: 状态（精确）。

        Returns:
            int: 记录条数。
        """
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(*self._scope_where(), *self._filter_conditions(keyword=keyword, status=status))
        )
        return int((await self._session.execute(statement)).scalar_one())

    def _filter_conditions(
        self, *, keyword: str | None, status: str | None
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """组装列表 / 统计筛选条件。

        Args:
            keyword: 关键字（角色码 / 名称模糊）。
            status: 状态（精确）。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: SQL 条件列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if keyword:
            pattern = f"%{keyword.lower()}%"
            conditions.add(
                or_(
                    func.lower(self._column("code")).like(pattern),
                    func.lower(self._column("name")).like(pattern),
                )
            )
        if status is not None:
            conditions.add(self._column("status") == status)
        return conditions


class UserRoleRepository(BaseDbRepository[SysUserRole]):
    """角色 × 用户分配仓储（`sys_user_role`）：按角色取已分配用户、计数与批量软删。"""

    model = SysUserRole
    sortable_fields = ConcurrentStableSet({"id"})

    async def list_by_role(self, role_id: int) -> ConcurrentStableList[SysUserRole]:
        """取角色的全部分配行（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysUserRole]: 分配行列表（按主键升序）。
        """
        statement = self._select().where(self._column("role_id") == role_id).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def list_user_ids_by_role(self, role_id: int) -> ConcurrentStableList[int]:
        """取角色已分配的用户主键清单（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[int]: 用户主键清单（按主键升序）。
        """
        statement = (
            select(self._column("user_id"))
            .where(*self._scope_where(), self._column("role_id") == role_id)
            .order_by(self._column("id").asc())
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_by_role(self, role_id: int) -> int:
        """统计角色已分配用户数（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            int: 已分配用户数。
        """
        statement = (
            select(func.count()).select_from(self.model).where(*self._scope_where(), self._column("role_id") == role_id)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def get_by_role_user(self, role_id: int, user_id: int) -> SysUserRole | None:
        """按角色 + 用户取分配行（不含软删除）。

        Args:
            role_id: 角色主键。
            user_id: 用户主键。

        Returns:
            SysUserRole | None: 分配行；不存在返回 None。
        """
        statement = self._select().where(self._column("role_id") == role_id, self._column("user_id") == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def delete_by_role(self, role_id: int, *, now: datetime | None = None) -> None:
        """批量软删角色的全部分配行（授权全量覆盖用）。

        Args:
            role_id: 角色主键。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or _utc_now()
        statement = (
            sa.update(self.model)
            .where(self._column("role_id") == role_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)


class RolePermissionRepository(BaseDbRepository[SysRolePermission]):
    """角色授权仓储（`sys_role_permission`）：按角色取授权行与批量软删。"""

    model = SysRolePermission
    sortable_fields = ConcurrentStableSet({"id"})

    async def list_by_role(self, role_id: int) -> ConcurrentStableList[SysRolePermission]:
        """取角色的全部授权行（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysRolePermission]: 授权行列表（按主键升序）。
        """
        statement = self._select().where(self._column("role_id") == role_id).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def delete_by_role(self, role_id: int, *, now: datetime | None = None) -> None:
        """批量软删角色的全部授权行（全量覆盖提交的先删步骤）。

        Args:
            role_id: 角色主键。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or _utc_now()
        statement = (
            sa.update(self.model)
            .where(self._column("role_id") == role_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)


class RoleFieldRepository(BaseDbRepository[SysRoleField]):
    """角色字段权限仓储（`sys_role_field`）：按角色取字段权限行与批量软删。"""

    model = SysRoleField
    sortable_fields = ConcurrentStableSet({"id"})

    async def list_by_role(self, role_id: int) -> ConcurrentStableList[SysRoleField]:
        """取角色的全部字段权限行（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysRoleField]: 字段权限行列表（按主键升序）。
        """
        statement = self._select().where(self._column("role_id") == role_id).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def delete_by_role(self, role_id: int, *, now: datetime | None = None) -> None:
        """批量软删角色的全部字段权限行（全量覆盖提交的先删步骤）。

        Args:
            role_id: 角色主键。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or _utc_now()
        statement = (
            sa.update(self.model)
            .where(self._column("role_id") == role_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)


class DataScopeRepository(BaseDbRepository[SysDataScope]):
    """角色数据权限仓储（`sys_data_scope`）：按角色取策略行与批量软删。"""

    model = SysDataScope
    sortable_fields = ConcurrentStableSet({"id"})

    async def list_by_role(self, role_id: int) -> ConcurrentStableList[SysDataScope]:
        """取角色的全部数据权限行（不含软删除）。

        Args:
            role_id: 角色主键。

        Returns:
            ConcurrentStableList[SysDataScope]: 数据权限行列表（按主键升序）。
        """
        statement = self._select().where(self._column("role_id") == role_id).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def delete_by_role(self, role_id: int, *, now: datetime | None = None) -> None:
        """批量软删角色的全部数据权限行（全量覆盖提交的先删步骤）。

        Args:
            role_id: 角色主键。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or _utc_now()
        statement = (
            sa.update(self.model)
            .where(self._column("role_id") == role_id, self._column("deleted_at").is_(None))
            .values(deleted_at=current, updated_at=current)
        )
        await self._session.execute(statement)
