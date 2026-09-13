"""平台库模型：业务模块注册（平台统一维护、租户可见不可增删）。

- `SysModule`：业务模块注册表（表前缀 / 错误码段 / 事件域等注册要素）。
- `SysModuleI18n`：多语言模块名附表（继承 `BaseModel`，`(module_id, locale, deleted_at)` 唯一）。
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SysModule(BaseModel):
    """业务模块注册表（`sys_module`）：注册要素四要素复合唯一。"""

    __tablename__ = "sys_module"
    __table_args__ = (
        UniqueConstraint("module_key", "deleted_at", name="uq_sys_module_key_deleted_at"),
        UniqueConstraint("table_prefix", "deleted_at", name="uq_sys_module_prefix_deleted_at"),
        UniqueConstraint("errcode_segment", "deleted_at", name="uq_sys_module_segment_deleted_at"),
        UniqueConstraint("event_domain", "deleted_at", name="uq_sys_module_domain_deleted_at"),
    )

    module_key: Mapped[str] = mapped_column(String(32), comment="模块简称（如 pur、sys）")
    name: Mapped[str] = mapped_column(String(128), comment="模块名（默认文案）")
    table_prefix: Mapped[str] = mapped_column(String(32), comment="表前缀（形如 pur_）")
    errcode_segment: Mapped[str] = mapped_column(String(8), comment="错误码段号（平台保留 01~09，业务 10 起）")
    event_domain: Mapped[str] = mapped_column(String(64), comment="事件域（全小写）")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled/planned）")


class SysModuleI18n(BaseModel):
    """多语言模块名附表（`sys_module_i18n`）。"""

    __tablename__ = "sys_module_i18n"
    __table_args__ = (
        UniqueConstraint(
            "module_id",
            "locale",
            "deleted_at",
            name="uq_sys_module_i18n_module_locale_deleted_at",
        ),
    )

    module_id: Mapped[int] = mapped_column(BigInteger, comment="模块 ID（逻辑外键 → sys_module.id）")
    locale: Mapped[str] = mapped_column(String(16), comment="语言标识（如 zh-CN）")
    name: Mapped[str] = mapped_column(String(128), comment="模块名文案")
