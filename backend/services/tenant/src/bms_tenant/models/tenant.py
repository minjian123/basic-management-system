"""租户注册模型：`sys_tenant`（平台服务库 `bms_tenant`；06_03 由共享基座库迁入本服务）。

- 数据所有权：**租户与配置服务**（写方唯一）；其他服务经租户注册只读契约取数。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant`）。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysTenant(BaseModel):
    """租户注册表（`sys_tenant`）：租户注册与路由依据（平台服务库）。

    `db_key` 为**废弃列**（06_01 起不再写入）：服务化后租户库键一律由
    `tenant_{service}_{code}` 派生，注册表不再持有数据源键；物理删列另立任务。
    """

    __tablename__ = "sys_tenant"
    __table_args__ = (UniqueConstraint("code", "deleted_at", name="uq_sys_tenant_code_deleted_at"),)

    code: Mapped[str] = mapped_column(String(64), comment="租户编码（全小写）")
    name: Mapped[str] = mapped_column(String(128), comment="租户名称")
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, comment="子域名")
    db_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="已废弃（06_01 起不再写入；库键由 tenant_{service}_{code} 派生）",
    )
    status: Mapped[str] = mapped_column(String(16), default="active", comment="状态（active/suspended）")
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="到期时间（UTC）")
