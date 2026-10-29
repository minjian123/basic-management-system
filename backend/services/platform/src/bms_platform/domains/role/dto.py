"""角色业务域数据 DTO：域公共出口只交本模块的不可变对象（D6 出口导出面）。

字段与能力契约的条目模型一一对应（`schemas/role.py` 的 `RoleItem` / `RoleDetail` /
`RolePermissionEntryItem` / `RoleFieldEntryItem` / `RoleDataScopeEntryItem`），
`from_model` 是**唯一**的模型 → DTO 转换入口：只做字段拷贝，不查询、不遍历关系
（跨域懒加载等价于隐式读表）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.objects import BaseValueObject
from bms_core.models.platform.role import ROLE_TYPE_CUSTOM, SysDataScope, SysRole, SysRoleField, SysRolePermission

__all__ = [
    "AssignedUser",
    "RoleDataScopeEntry",
    "RoleDetail",
    "RoleFieldGrant",
    "RolePermissionEntry",
    "RoleSummary",
]


@dataclass(frozen=True)
class RoleSummary(BaseValueObject):
    """角色行（列表 / 详情共用部分）。"""

    id: int
    """角色主键。"""

    code: str
    """角色码。"""

    name: str
    """角色名称。"""

    status: str
    """状态（enabled/disabled）。"""

    role_type: str
    """角色类型（custom/system/security/audit）。"""

    builtin: bool
    """是否内置角色（按 `role_type` 判定，非 custom 即内置）。"""

    @classmethod
    def from_model(cls, row: SysRole) -> RoleSummary:
        """由角色记录构造摘要。

        Args:
            row: 角色 ORM 记录。

        Returns:
            RoleSummary: 角色摘要。
        """
        return cls(
            id=row.id,
            code=row.code,
            name=row.name,
            status=row.status,
            role_type=row.role_type,
            builtin=row.role_type != ROLE_TYPE_CUSTOM,
        )


@dataclass(frozen=True)
class RoleDetail(RoleSummary):
    """角色详情（摘要 + 乐观锁版本与审计四列）。"""

    version: int
    """乐观锁版本。"""

    created_at: datetime
    """创建时间（UTC，无时区）。"""

    created_by: int | None
    """创建人。"""

    updated_at: datetime
    """更新时间（UTC，无时区）。"""

    updated_by: int | None
    """更新人。"""

    @classmethod
    def from_model(cls, row: SysRole) -> RoleDetail:
        """由角色记录构造详情。

        Args:
            row: 角色 ORM 记录。

        Returns:
            RoleDetail: 角色详情。
        """
        return cls(
            id=row.id,
            code=row.code,
            name=row.name,
            status=row.status,
            role_type=row.role_type,
            builtin=row.role_type != ROLE_TYPE_CUSTOM,
            version=row.version,
            created_at=row.created_at,
            created_by=row.created_by,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )


@dataclass(frozen=True)
class RolePermissionEntry(BaseValueObject):
    """角色授权条目（菜单 / 表单 / 操作）。"""

    id: int
    """授权行主键。"""

    perm_type: str
    """授权类型（menu/form/action）。"""

    target_id: int
    """授权目标 ID。"""

    source_menu_id: int
    """来源菜单入口 ID（0 = 表单级直接授予）。"""

    @classmethod
    def from_model(cls, row: SysRolePermission) -> RolePermissionEntry:
        """由授权记录构造条目。

        Args:
            row: 授权 ORM 记录。

        Returns:
            RolePermissionEntry: 授权条目。
        """
        return cls(
            id=row.id,
            perm_type=row.perm_type,
            target_id=row.target_id,
            source_menu_id=row.source_menu_id,
        )


@dataclass(frozen=True)
class RoleFieldGrant(BaseValueObject):
    """角色字段权限（默认全开，只存收窄项）。"""

    id: int
    """字段权限行主键。"""

    form_id: int
    """表单 ID。"""

    field_id: int
    """字段 ID。"""

    visible: bool
    """是否可见。"""

    editable: bool
    """是否可编辑（不可见即不可编辑）。"""

    source_menu_id: int
    """来源菜单入口 ID（0 = 表单级直接授予）。"""

    @classmethod
    def from_model(cls, row: SysRoleField) -> RoleFieldGrant:
        """由字段权限记录构造条目。

        Args:
            row: 字段权限 ORM 记录。

        Returns:
            RoleFieldGrant: 字段权限条目。
        """
        return cls(
            id=row.id,
            form_id=row.form_id,
            field_id=row.field_id,
            visible=row.visible,
            editable=row.editable,
            source_menu_id=row.source_menu_id,
        )


@dataclass(frozen=True)
class RoleDataScopeEntry(BaseValueObject):
    """角色数据权限条目（角色 × 字典 × 策略 → 结构化配置）。"""

    id: int
    """数据权限行主键。"""

    data_source_key: str
    """字典标识（业务码字符串）。"""

    policy_type: str
    """策略类型（select/region/match/extension）。"""

    config: ConcurrentStableList[ConcurrentStableDict[str, object]]
    """结构化策略配置（按策略分结构）。"""

    @classmethod
    def from_model(cls, row: SysDataScope) -> RoleDataScopeEntry:
        """由数据权限记录构造条目。

        Args:
            row: 数据权限 ORM 记录。

        Returns:
            RoleDataScopeEntry: 数据权限条目。
        """
        return cls(
            id=row.id,
            data_source_key=row.data_source_key,
            policy_type=row.policy_type,
            config=ConcurrentStableList(row.config),
        )


@dataclass(frozen=True)
class AssignedUser(BaseValueObject):
    """已分配用户行（角色详情里展示，数据来自用户域 DTO 投影）。"""

    user_id: int
    """用户主键。"""

    username: str
    """登录账号。"""

    name: str
    """用户昵称 / 显示名。"""

    status: str
    """账号状态（enabled/disabled）。"""
