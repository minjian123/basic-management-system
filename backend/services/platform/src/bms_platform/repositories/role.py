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
from bms_platform.models.user import SysUser


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

    async def list_by_ids(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[SysRole]:
        """按主键集合取角色（不含软删除；豁免层级判定用）。

        Args:
            role_ids: 角色主键集合（空集返回空列表）。

        Returns:
            ConcurrentStableList[SysRole]: 角色列表（按主键升序）。
        """
        if not role_ids:
            return ConcurrentStableList()
        statement = self._select().where(self._column("id").in_(tuple(role_ids))).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

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

    async def list_role_ids_by_user(self, user_id: int) -> ConcurrentStableList[int]:
        """取用户已分配的角色主键清单（不含软删除；主体链解析用）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[int]: 角色主键清单（按主键升序）。
        """
        statement = (
            select(self._column("role_id"))
            .where(*self._scope_where(), self._column("user_id") == user_id)
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

    async def count_by_user(self, user_id: int) -> int:
        """统计用户已分配角色数（不含软删除；用户删除前的引用校验用）。

        Args:
            user_id: 用户主键。

        Returns:
            int: 已分配角色数。
        """
        statement = (
            select(func.count()).select_from(self.model).where(*self._scope_where(), self._column("user_id") == user_id)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def list_by_user(self, user_id: int) -> ConcurrentStableList[SysUserRole]:
        """取用户的全部生效分配行（不含软删除；编排全量覆盖用）。

        Args:
            user_id: 用户主键。

        Returns:
            ConcurrentStableList[SysUserRole]: 分配行列表（按主键升序）。
        """
        statement = self._select().where(self._column("user_id") == user_id).order_by(self._column("id").asc())
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def soft_delete_by_user_except(
        self,
        user_id: int,
        keep_role_ids: ConcurrentStableSet[int],
        *,
        now: datetime | None = None,
    ) -> None:
        """按用户批量软删「保留集合之外」的分配行（全量覆盖的先删步骤）。

        Args:
            user_id: 用户主键。
            keep_role_ids: 需保留的角色主键集合（空集 = 全部软删）。
            now: 当前时间（UTC naive；None 取当前 UTC）。
        """
        current = now or _utc_now()
        statement = sa.update(self.model).where(
            self._column("user_id") == user_id,
            self._column("deleted_at").is_(None),
        )
        if keep_role_ids:
            statement = statement.where(self._column("role_id").not_in(tuple(keep_role_ids)))
        await self._session.execute(statement.values(deleted_at=current, updated_at=current))

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

    async def get_deleted_by_role_user(self, role_id: int, user_id: int) -> SysUserRole | None:
        """按角色 + 用户取**已软删**的分配行（解绑后再分配时恢复原行用）。

        Args:
            role_id: 角色主键。
            user_id: 用户主键。

        Returns:
            SysUserRole | None: 最近一条已软删分配行；不存在返回 None。
        """
        statement = (
            self._select(include_soft_delete=False)
            .where(
                self._column("role_id") == role_id,
                self._column("user_id") == user_id,
                self._column("deleted_at").is_not(None),
            )
            .order_by(self._column("id").desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalars().first()

    async def restore(self, item_id: int) -> bool:
        """恢复软删除的分配行（清 `deleted_at`；不校验作用域外记录）。

        Args:
            item_id: 分配行主键。

        Returns:
            bool: 恢复成功 True；记录不存在 False。
        """
        statement = self._select(include_soft_delete=False).where(self._column("id") == item_id)
        item = (await self._session.execute(statement)).scalar_one_or_none()
        if item is None:
            return False
        item.restore()
        await self._session.flush()
        return True

    async def soft_delete_by_role_user(self, role_id: int, user_id: int) -> bool:
        """按角色 + 用户软删**生效中**的分配行（解绑）。

        Args:
            role_id: 角色主键。
            user_id: 用户主键。

        Returns:
            bool: 命中并软删 True；无生效行 False。
        """
        item = await self.get_by_role_user(role_id, user_id)
        if item is None:
            return False
        item.soft_delete()
        await self._session.flush()
        return True

    async def list_filtered_by_role(
        self,
        role_id: int,
        query: BasePageQuery,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> ConcurrentStableList[SysUserRole]:
        """按筛选条件分页查询角色的分配行（用户属性经同库子查询过滤）。

        Args:
            role_id: 角色主键。
            query: 页码分页请求（含排序参数）。
            keyword: 关键字（匹配用户账号 / 姓名，大小写不敏感）。
            status: 用户状态（精确）。

        Returns:
            ConcurrentStableList[SysUserRole]: 当前页分配行。
        """
        statement = (
            self._apply_sort(self._select(), self._resolve_sort(query))
            .where(*self._assignment_conditions(role_id, keyword=keyword, status=status))
            .limit(query.size)
            .offset((query.page - 1) * query.size)
        )
        return ConcurrentStableList((await self._session.execute(statement)).scalars().all())

    async def count_filtered_by_role(
        self, role_id: int, *, keyword: str | None = None, status: str | None = None
    ) -> int:
        """按筛选条件统计角色的分配行数（与 `list_filtered_by_role` 同口径）。

        Args:
            role_id: 角色主键。
            keyword: 关键字（匹配用户账号 / 姓名）。
            status: 用户状态（精确）。

        Returns:
            int: 记录条数。
        """
        statement = (
            select(func.count())
            .select_from(self.model)
            .where(*self._scope_where(), *self._assignment_conditions(role_id, keyword=keyword, status=status))
        )
        return int((await self._session.execute(statement)).scalar_one())

    def _assignment_conditions(
        self, role_id: int, *, keyword: str | None, status: str | None
    ) -> ConcurrentStableList[ColumnElement[bool]]:
        """组装「按角色取分配行」的筛选条件（用户属性经 `sys_user` 同库子查询）。

        Args:
            role_id: 角色主键。
            keyword: 关键字（用户账号 / 姓名模糊）。
            status: 用户状态（精确）。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: SQL 条件列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        conditions.add(self._column("role_id") == role_id)
        if keyword or status is not None:
            user_scope = select(SysUser.id).where(SysUser.deleted_at.is_(None))
            if keyword:
                pattern = f"%{keyword.lower()}%"
                user_scope = user_scope.where(
                    or_(
                        func.lower(SysUser.username).like(pattern),
                        func.lower(SysUser.name).like(pattern),
                    )
                )
            if status is not None:
                user_scope = user_scope.where(SysUser.status == status)
            conditions.add(self._column("user_id").in_(user_scope))
        return conditions


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

    async def list_by_roles(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[SysRolePermission]:
        """取一组角色的全部授权行（不含软删除；权限聚合一批取，避免 N 次查询）。

        Args:
            role_ids: 角色主键集合（空集返回空列表）。

        Returns:
            ConcurrentStableList[SysRolePermission]: 授权行列表（按主键升序）。
        """
        if not role_ids:
            return ConcurrentStableList()
        statement = (
            self._select().where(self._column("role_id").in_(tuple(role_ids))).order_by(self._column("id").asc())
        )
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

    async def list_by_roles(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[SysRoleField]:
        """取一组角色的全部字段权限行（不含软删除；字段权限聚合一批取，避免 N 次查询）。

        Args:
            role_ids: 角色主键集合（空集返回空列表）。

        Returns:
            ConcurrentStableList[SysRoleField]: 字段权限行列表（按主键升序）。
        """
        if not role_ids:
            return ConcurrentStableList()
        statement = (
            self._select().where(self._column("role_id").in_(tuple(role_ids))).order_by(self._column("id").asc())
        )
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

    async def list_by_roles(self, role_ids: ConcurrentStableSet[int]) -> ConcurrentStableList[SysDataScope]:
        """取一组角色的全部数据权限行（不含软删除；快照聚合一批取，避免 N 次查询）。

        Args:
            role_ids: 角色主键集合（空集返回空列表）。

        Returns:
            ConcurrentStableList[SysDataScope]: 数据权限行列表（按主键升序）。
        """
        if not role_ids:
            return ConcurrentStableList()
        statement = (
            self._select().where(self._column("role_id").in_(tuple(role_ids))).order_by(self._column("id").asc())
        )
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
