"""权限元数据模型：业务码 / 动作码 / 权限码字典（含多语言附表）。

- 归属：业务域 `permission_meta`（承载服务 `platform`，库类别 `platform`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_business.md` / `sys_action.md` / `sys_permission.md`）。

三词分治（2026-10-10 拍板）：**业务码**（`sys_business`，纯资源维度）、**动作码**（`sys_action`，全局动词维度）、
**权限码**（`sys_permission`，业务码 × 动作码组合）——业务级由「入口授权」独立判定，接口/数据访问走权限码。
"""

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysBusiness(BaseModel):
    """业务码字典（`sys_business`）：纯资源维度（权限码左半），平台统一维护、租户侧只读。"""

    __tablename__ = "sys_business"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_business_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_business_form_key_deleted_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="business", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="业务码（小写单词，资源维度）")
    name: Mapped[str] = mapped_column(String(128), comment="名称（默认文案）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysBusinessI18n(BaseModel):
    """业务码名称多语言附表（`sys_business_i18n`）。"""

    __tablename__ = "sys_business_i18n"
    __table_args__ = (
        UniqueConstraint("business_id", "locale", "deleted_at", name="uq_sys_business_i18n_business_locale_deleted_at"),
    )

    business_id: Mapped[int] = mapped_column(BigInteger, comment="业务码 ID（逻辑外键 → sys_business.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="业务名的该语言文案")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )


class SysAction(BaseModel):
    """动作码字典（`sys_action`）：全局动词维度（权限码右半），平台统一维护、租户侧只读。"""

    __tablename__ = "sys_action"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_action_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_action_form_key_deleted_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="action", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="动作码（如 query/create/manage；全局唯一动词）")
    name: Mapped[str] = mapped_column(String(128), comment="名称（默认文案）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysActionI18n(BaseModel):
    """动作码名称多语言附表（`sys_action_i18n`）。"""

    __tablename__ = "sys_action_i18n"
    __table_args__ = (
        UniqueConstraint("action_id", "locale", "deleted_at", name="uq_sys_action_i18n_action_locale_deleted_at"),
    )

    action_id: Mapped[int] = mapped_column(BigInteger, comment="动作码 ID（逻辑外键 → sys_action.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="动作名的该语言文案")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )


class SysPermission(BaseModel):
    """权限码（`sys_permission`）：业务码 × 动作码组合，平台统一维护的**真正权限码**。

    名称由「业务名 + 动作名」组合生成，不落独立名称列（多语言复用两张字典的 `_i18n` 附表）；
    组合为受控可授项：按钮挂接与角色授权只能选已存在的权限码。
    """

    __tablename__ = "sys_permission"
    __table_args__ = (
        UniqueConstraint("business_id", "action_id", "deleted_at", name="uq_sys_permission_business_action_deleted_at"),
    )

    business_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="业务码 ID（逻辑外键 → sys_business.id）")
    action_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="动作码 ID（逻辑外键 → sys_action.id）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
