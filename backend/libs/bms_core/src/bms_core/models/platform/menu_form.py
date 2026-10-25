"""菜单元数据模型：菜单 / 表单 / 按钮 / 字段（含多语言附表）。

- 归属：业务域 `menu_form`（承载服务 `platform`，库类别 `platform`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_menu.md` 等表文件）；
- 业务码 / 动作码 / 权限码三字典见 `bms_core.models.platform.permission_meta`（另域）。

挂接链：菜单 ↔ 表单**多对多**（经关联表 `sys_menu_form`）、表单 1:1 业务、按钮 1:1 挂**权限码**、字段挂表单。
"""

from sqlalchemy import BigInteger, Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysMenu(BaseModel):
    """菜单树（`sys_menu`）：动态路由依据；1:1 挂接表单。"""

    __tablename__ = "sys_menu"
    __table_args__ = (UniqueConstraint("path", "deleted_at", name="uq_sys_menu_path_deleted_at"),)

    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, index=True, comment="父菜单 ID（0 为根）")
    name: Mapped[str] = mapped_column(String(128), comment="菜单名（默认文案）")
    path: Mapped[str] = mapped_column(String(255), comment="前端路由路径（/ 开头）")
    component: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="视图组件标识（可空 = 目录节点）")
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="完整 icon key")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序（升序）")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, comment="仅隐藏侧栏入口（权限仍生效）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysMenuI18n(BaseModel):
    """菜单名多语言附表（`sys_menu_i18n`）。"""

    __tablename__ = "sys_menu_i18n"
    __table_args__ = (
        UniqueConstraint("menu_id", "locale", "deleted_at", name="uq_sys_menu_i18n_menu_locale_deleted_at"),
    )

    menu_id: Mapped[int] = mapped_column(BigInteger, comment="菜单 ID（逻辑外键 → sys_menu.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="菜单名的该语言文案")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )


class SysForm(BaseModel):
    """表单（`sys_form`）：1:1 挂业务权限；菜单入口经关联表 `sys_menu_form` **多对多**。"""

    __tablename__ = "sys_form"
    __table_args__ = (UniqueConstraint("business_id", "deleted_at", name="uq_sys_form_business_id_deleted_at"),)

    business_id: Mapped[int] = mapped_column(BigInteger, comment="所属业务码 ID（逻辑外键 → sys_business.id；1:1）")
    component: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="表单视图组件标识")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")


class SysMenuForm(BaseModel):
    """菜单 ↔ 表单关联（`sys_menu_form`）：多对多（多入口指向同一表单；表单可无入口）。"""

    __tablename__ = "sys_menu_form"
    __table_args__ = (
        UniqueConstraint("menu_id", "form_id", "deleted_at", name="uq_sys_menu_form_menu_form_deleted_at"),
    )

    menu_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="菜单 ID（逻辑外键 → sys_menu.id；多对多）")
    form_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="表单 ID（逻辑外键 → sys_form.id；多对多）")


class SysButton(BaseModel):
    """表单按钮（`sys_button`）：按钮 1:1 挂**权限码**；默认无任何按钮权限。"""

    __tablename__ = "sys_button"
    __table_args__ = (
        UniqueConstraint("form_id", "permission_id", "deleted_at", name="uq_sys_button_form_permission_deleted_at"),
    )

    form_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属表单 ID（逻辑外键 → sys_form.id）")
    permission_id: Mapped[int] = mapped_column(
        BigInteger, index=True, comment="挂接权限码 ID（逻辑外键 → sys_permission.id；1:1）"
    )
    name: Mapped[str] = mapped_column(String(128), comment="按钮名（界面可见文本）")
    type: Mapped[str] = mapped_column(String(16), default="toolbar", comment="按钮形态（toolbar/interface）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同表内排序（升序）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )


class SysField(BaseModel):
    """表单字段（`sys_field`）：字段权限控制依据。"""

    __tablename__ = "sys_field"
    __table_args__ = (UniqueConstraint("form_id", "field_key", "deleted_at", name="uq_sys_field_form_key_deleted_at"),)

    form_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="所属表单 ID（逻辑外键 → sys_form.id）")
    field_key: Mapped[str] = mapped_column(String(64), comment="字段键（表单内唯一）")
    name: Mapped[str] = mapped_column(String(128), comment="字段名（默认文案）")
    type: Mapped[str] = mapped_column(String(32), comment="字段类型（组件语义键）")
    sort: Mapped[int] = mapped_column(Integer, default=0, comment="同表内排序（升序）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )


class SysFieldI18n(BaseModel):
    """表单字段名多语言附表（`sys_field_i18n`）。"""

    __tablename__ = "sys_field_i18n"
    __table_args__ = (
        UniqueConstraint("field_id", "locale", "deleted_at", name="uq_sys_field_i18n_field_locale_deleted_at"),
    )

    field_id: Mapped[int] = mapped_column(BigInteger, comment="字段 ID（逻辑外键 → sys_field.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="字段名的该语言文案")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )
