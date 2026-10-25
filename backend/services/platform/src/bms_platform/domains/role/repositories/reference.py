"""角色授权引用探测仓储：删除许可判断（`sys_role_permission` / `sys_role_field`）。

- 归属业务域 `role`（`sys_role_permission` / `sys_role_field` 的写者与所有者）；
- 用途：菜单 / 表单 / 按钮 / 字段 / 权限码 / 业务码删除前，判断是否已被角色授权引用（只读探测）；
- 探测对象跨库（平台库元数据 + 租户库授权），故由调用方按「租户库工作单元」构造。
"""

import sqlalchemy as sa
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.role import (
    PERM_TYPE_FORM,
    PERM_TYPE_MENU,
    PERM_TYPE_PERMISSION,
    SysRoleField,
    SysRolePermission,
)
from bms_core.repositories.base_db_repository import BaseDbRepository


class MetadataReferenceRepository(BaseDbRepository[SysRolePermission]):
    """元数据引用探测（只读）：菜单 / 表单 / 权限码 / 字段是否被角色授权引用。

    授权关系归角色域（`sys_role_permission` / `sys_role_field`），本仓储只做只读计数，
    供养护菜单 / 表单 / 权限码的删除与停用前置校验（`40206`）。
    """

    model = SysRolePermission

    async def count_menu_refs(self, menu_id: int) -> int:
        """统计引用某菜单的角色授权数（菜单授权目标或任一带源入口的授权）。

        Args:
            menu_id: 菜单 ID。

        Returns:
            int: 引用数（活动行）。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysRolePermission)
            .where(
                SysRolePermission.deleted_at.is_(None),
                sa.or_(
                    sa.and_(SysRolePermission.perm_type == PERM_TYPE_MENU, SysRolePermission.target_id == menu_id),
                    SysRolePermission.source_menu_id == menu_id,
                ),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def count_form_refs(self, form_id: int) -> int:
        """统计引用某表单的角色授权数（表单授权目标或来源菜单指向该表单入口）。

        Args:
            form_id: 表单 ID。

        Returns:
            int: 引用数（活动行）。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysRolePermission)
            .where(
                SysRolePermission.deleted_at.is_(None),
                SysRolePermission.perm_type == PERM_TYPE_FORM,
                sa.or_(SysRolePermission.target_id == form_id, SysRolePermission.source_menu_id == form_id),
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def count_permission_refs(self, permission_id: int) -> int:
        """统计引用某权限码的角色授权数。

        Args:
            permission_id: 权限码 ID。

        Returns:
            int: 引用数（活动行）。
        """
        statement = (
            select(sa.func.count())
            .select_from(SysRolePermission)
            .where(
                SysRolePermission.deleted_at.is_(None),
                SysRolePermission.perm_type == PERM_TYPE_PERMISSION,
                SysRolePermission.target_id == permission_id,
            )
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def count_field_refs(self, *, form_id: int | None = None, field_id: int | None = None) -> int:
        """统计引用某表单 / 字段的角色字段权限数。

        Args:
            form_id: 表单 ID（可空）。
            field_id: 字段 ID（可空）。

        Returns:
            int: 引用数（活动行；两参皆空返回 0）。
        """
        if form_id is None and field_id is None:  # pragma: no cover - 调用方至少传一个条件
            return 0
        conditions: ConcurrentStableList[sa.ColumnElement[bool]] = ConcurrentStableList(
            [SysRoleField.deleted_at.is_(None)]
        )
        if form_id is not None:
            conditions.append(SysRoleField.form_id == form_id)
        if field_id is not None:
            conditions.append(SysRoleField.field_id == field_id)
        statement = select(sa.func.count()).select_from(SysRoleField).where(*conditions)
        return int((await self._session.execute(statement)).scalar_one())
