"""角色域模型：`sys_role` / `sys_user_role` / `sys_role_permission` / `sys_role_field` / `sys_data_scope`。

- 数据所有权：**平台服务**（platform 服务租户库 `bms_platform_{code}`，与 `sys_config` / `sys_user_extension` 同库）。
- 域内引用：角色域表之间以 `role_id` 逻辑引用（同库）。
- 跨库 / 跨服务逻辑引用（只存 ID，不 join、不建物理外键）：
  - 授权目标 `sys_menu` / `sys_form` / `sys_action` 在 **platform 平台库**（同服务、不同库）→ 校验经平台侧元数据完成；
  - `sys_user_role.user_id` 指向 **org 服务租户库**的 `sys_user`（跨服务）→ 有效性经 org 只读接口核验。
- 来源标记：`source_menu_id = 0` 表示「表单级直接授予」（不用 NULL，规避唯一约束在 NULL 上的跨库语义差异）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_role` 等 5 表）。
"""

from sqlalchemy import BigInteger, Boolean, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.base import BaseModel, StableJson

PERM_TYPE_MENU = "menu"
"""授权类型：菜单入口（仅菜单入口；勾选连带授予其表单查看权限）。"""

PERM_TYPE_FORM = "form"
"""授权类型：表单（「查看」= 表单权限；可由菜单入口连带或表单级直接授予）。"""

PERM_TYPE_ACTION = "action"
"""授权类型：操作（动作，默认无）。"""

PERM_TYPES: tuple[str, ...] = (PERM_TYPE_MENU, PERM_TYPE_FORM, PERM_TYPE_ACTION)
"""授权类型取值清单。"""

POLICY_TYPE_SELECT = "select"
"""数据权限策略：数据选择（勾选字典数据）。"""

POLICY_TYPE_REGION = "region"
"""数据权限策略：数据区域（开始值 / 结束值）。"""

POLICY_TYPE_MATCH = "match"
"""数据权限策略：数据匹配（字段 + 通配符值）。"""

POLICY_TYPE_EXTENSION = "extension"
"""数据权限策略：扩展权限（注册的后端筛选器 + 参数 JSON）。"""

POLICY_TYPES: tuple[str, ...] = (POLICY_TYPE_SELECT, POLICY_TYPE_REGION, POLICY_TYPE_MATCH, POLICY_TYPE_EXTENSION)
"""数据权限策略取值清单。"""

NO_SOURCE_MENU_ID = 0
"""来源占位：表单级直接授予（非任何菜单入口连带）。"""


class SysRole(BaseModel):
    """角色（`sys_role`）：角色码 / 名称 / 状态；内置角色按配置常量判定（不设库列）。"""

    __tablename__ = "sys_role"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_role_code_deleted_at"),
        Index("idx_sys_role_status", "status"),
    )

    code: Mapped[str] = mapped_column(String(64), comment="角色码（租户内唯一；创建后不可修改）")
    name: Mapped[str] = mapped_column(String(128), comment="角色名称")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysUserRole(BaseModel):
    """角色 × 用户分配（`sys_user_role`）：与用户管理页「用户分配角色」同一张关系表。"""

    __tablename__ = "sys_user_role"
    __table_args__ = (
        UniqueConstraint("role_id", "user_id", "deleted_at", name="uq_sys_user_role_role_user_deleted_at"),
        Index("idx_sys_user_role_role_id", "role_id"),
        Index("idx_sys_user_role_user_id", "user_id"),
    )

    role_id: Mapped[int] = mapped_column(BigInteger, comment="角色主键（逻辑外键 sys_role.id，同库）")
    user_id: Mapped[int] = mapped_column(BigInteger, comment="用户主键（跨服务逻辑外键 sys_user.id，org 服务租户库）")


class SysRolePermission(BaseModel):
    """角色授权（`sys_role_permission`）：菜单 / 表单 / 操作；带来源 `source_menu_id` 判定可改性。"""

    __tablename__ = "sys_role_permission"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "perm_type",
            "target_id",
            "source_menu_id",
            "deleted_at",
            name="uq_sys_role_permission_role_type_target_source_deleted_at",
        ),
        Index("idx_sys_role_permission_role_type", "role_id", "perm_type"),
        Index("idx_sys_role_permission_target", "target_id"),
    )

    role_id: Mapped[int] = mapped_column(BigInteger, comment="角色主键（逻辑外键 sys_role.id，同库）")
    perm_type: Mapped[str] = mapped_column(String(16), comment="授权类型（menu/form/action）")
    target_id: Mapped[int] = mapped_column(
        BigInteger,
        comment="授权目标 ID（平台实体雪花 ID：sys_menu/sys_form/sys_action；platform 平台库跨库逻辑外键）",
    )
    source_menu_id: Mapped[int] = mapped_column(
        BigInteger, default=NO_SOURCE_MENU_ID, comment="来源菜单入口 ID（0 = 表单级直接授予）"
    )


class SysRoleField(BaseModel):
    """角色字段权限（`sys_role_field`）：默认全开，只存收窄项；带来源 `source_menu_id`。"""

    __tablename__ = "sys_role_field"
    __table_args__ = (
        UniqueConstraint(
            "role_id",
            "form_id",
            "field_id",
            "source_menu_id",
            "deleted_at",
            name="uq_sys_role_field_role_form_field_source_deleted_at",
        ),
        Index("idx_sys_role_field_role_form", "role_id", "form_id"),
    )

    role_id: Mapped[int] = mapped_column(BigInteger, comment="角色主键（逻辑外键 sys_role.id，同库）")
    form_id: Mapped[int] = mapped_column(
        BigInteger, comment="表单 ID（平台实体，platform 平台库跨库逻辑外键 sys_form.id）"
    )
    field_id: Mapped[int] = mapped_column(
        BigInteger, comment="字段 ID（平台实体，platform 平台库跨库逻辑外键 sys_field.id）"
    )
    visible: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否可见（false = 读时过滤）")
    editable: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否可编辑（false = 写时拒绝）")
    source_menu_id: Mapped[int] = mapped_column(
        BigInteger, default=NO_SOURCE_MENU_ID, comment="来源菜单入口 ID（0 = 表单级直接授予）"
    )


class SysDataScope(BaseModel):
    """角色数据权限（`sys_data_scope`）：角色 × 字典 × 策略 → `config`（只选不编）。"""

    __tablename__ = "sys_data_scope"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "dict_type_id", "policy_type", "deleted_at", name="uq_sys_data_scope_role_dict_policy_deleted_at"
        ),
        Index("idx_sys_data_scope_role_id", "role_id"),
    )

    role_id: Mapped[int] = mapped_column(BigInteger, comment="角色主键（逻辑外键 sys_role.id，同库）")
    dict_type_id: Mapped[int] = mapped_column(
        BigInteger, comment="字典类型 ID（platform 服务租户库实体，同服务同库逻辑外键 sys_dict_type.id）"
    )
    policy_type: Mapped[str] = mapped_column(String(16), comment="策略类型（select/region/match/extension）")
    config: Mapped[ConcurrentStableList[ConcurrentStableDict[str, object]]] = mapped_column(
        StableJson, default=list, comment="结构化策略配置（只选不编，按策略分结构）"
    )
