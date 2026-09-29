"""租户库名对照模型：`sys_tenant_database`（平台服务库 `bms_tenant`）。

- 语义：租户主键 ↔ 库名基对照；一租户一行，各服务共享同一基（10_01 §3.2）。
- 库键 / 库名保持 code 派生（`tenant_{db_basis}` / `bms_{service}_{db_basis}`），`db_basis`
  为**创建时冻结的库名基**，不随租户编码变更而变（避免「code 复用 = 物理层串号」）。
- 读写归属：写方 = tenant 服务（租户开通 / 建库 / 种子时与 `sys_tenant` 同事务写入）；
  读方 = 租户源（随快照 / 契约下发 `db_basis`）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant_database`）。
"""

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysTenantDatabase(BaseModel):
    """租户库名对照（`sys_tenant_database`）：租户主键 → 库名基。"""

    __tablename__ = "sys_tenant_database"
    __table_args__ = (UniqueConstraint("tenant_id", "deleted_at", name="uq_sys_tenant_database_tenant_deleted_at"),)

    tenant_id: Mapped[int] = mapped_column(BigInteger, comment="租户主键（同库逻辑外键 → sys_tenant.id，只持值）")
    db_basis: Mapped[str] = mapped_column(String(64), comment="库名基（创建时冻结的租户编码，稳定不可变）")
