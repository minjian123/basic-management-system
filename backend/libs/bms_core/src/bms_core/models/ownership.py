"""表归属登记模型：`sys_table_ownership`（平台链；与服务目录同源机制，归属 `platform`）。

- 单一来源为 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`（代码常量）；
  本表为**落库登记与对账**载体（`ops/seed_tables.py` 幂等 upsert、`ops/check_tables.py` 双向对账）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_table_ownership`）。
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysTableOwnership(BaseModel):
    """表归属登记表（`sys_table_ownership`）：一表一行，登记归属服务与库类别。"""

    __tablename__ = "sys_table_ownership"
    __table_args__ = (UniqueConstraint("table_name", "deleted_at", name="uq_sys_table_ownership_name_deleted_at"),)

    table_name: Mapped[str] = mapped_column(String(64), comment="表名")
    owner: Mapped[str] = mapped_column(String(32), comment="归属服务标识（`*` = 每服务自有）")
    datasource: Mapped[str] = mapped_column(
        String(16), default="tenant", comment="库类别（platform / tenant / archive / both）"
    )
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled / planned）")
    note: Mapped[str] = mapped_column(String(255), default="", comment="说明")
