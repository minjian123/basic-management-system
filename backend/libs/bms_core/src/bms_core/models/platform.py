"""平台库模型：业务模块注册（平台统一维护、租户可见不可增删）。

- `SysModule`：业务模块注册表（表前缀 / 错误码段 / 事件域等注册要素）。
- `SysModuleI18n`：多语言模块名附表（继承 `BaseModel`，`(module_id, locale, deleted_at)` 唯一）。
- 表结构以《数据库设计》数据表文件为唯一事实源。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysTenant(BaseModel):
    """租户注册表（`sys_tenant`）：租户注册与路由依据（平台库）。"""

    __tablename__ = "sys_tenant"
    __table_args__ = (UniqueConstraint("code", "deleted_at", name="uq_sys_tenant_code_deleted_at"),)

    code: Mapped[str] = mapped_column(String(64), comment="租户编码（全小写）")
    name: Mapped[str] = mapped_column(String(128), comment="租户名称")
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, comment="子域名")
    db_key: Mapped[str] = mapped_column(String(64), comment="数据源键（tenant_{code}）")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="状态（active/suspended）")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="到期时间（UTC）")


class SysModule(BaseModel):
    """服务目录与契约登记表（`sys_module`）：服务与模块同源登记。

    - 一行 = 一个登记单元，同一行可同时承载「服务」（`service_key`）与「模块」（`module_key`）维度。
    - DB 级复合唯一仅保留非空列 `module_key` / `table_prefix` / `event_domain`；
      `service_key` / `errcode_segment` 可空，其唯一性由启动 / CI 校验承担（规避达梦多 NULL 差异）。
    """

    __tablename__ = "sys_module"
    __table_args__ = (
        UniqueConstraint("module_key", "deleted_at", name="uq_sys_module_key_deleted_at"),
        UniqueConstraint("table_prefix", "deleted_at", name="uq_sys_module_prefix_deleted_at"),
        UniqueConstraint("event_domain", "deleted_at", name="uq_sys_module_domain_deleted_at"),
    )

    module_key: Mapped[str] = mapped_column(String(32), comment="行登记标识（模块简称 / 服务标识）")
    service_key: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="服务维度标识（微服务工程名，如 platform）"
    )
    name: Mapped[str] = mapped_column(String(128), comment="名称（默认文案）")
    table_prefix: Mapped[str] = mapped_column(String(32), comment="表前缀（形如 pur_）")
    business_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="业务权限码（sys_business.code）"
    )
    errcode_segment: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="错误码段号（产品 10 起；平台域 01~04）"
    )
    event_domain: Mapped[str] = mapped_column(String(64), comment="事件域（全小写）")
    service_group: Mapped[str] = mapped_column(
        String(16), default="foundation", comment="归属分组（foundation/capability/product）"
    )
    build_batch: Mapped[int] = mapped_column(Integer, default=0, comment="建设批次（0~3）")
    service_version: Mapped[str] = mapped_column(String(16), default="0.1.0", comment="服务版本（semver）")
    contract_version: Mapped[str] = mapped_column(String(16), default="0.1.0", comment="契约版本（semver）")
    product_key: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="产品标识（biz/cw；空=平台）")
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
