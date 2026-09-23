"""表归属登记表（`platform:platform` 链 0005，06_02 承接 06_03 遗留 1）。

Revision ID: 0005_sys_table_ownership
Revises: 0004_sys_outbox_event_version
Create Date: 2026-09-23

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- 字段 / 索引口径与 ORM 模型（`bms_core/models/ownership.py::SysTableOwnership`）逐项一致；
- 单一来源为代码常量 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`，本表为**落库登记与对账**
  载体（`ops/seed_tables.py` 幂等 upsert、`ops/check_tables.py` 双向对账、`platform` 服务启动期对账）；
- 表结构以《数据库设计》数据表文件 `sys_table_ownership.md` 为唯一事实源；
- 只建表不写种子（种子走 `ops/seed_tables.py` 幂等脚本）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_sys_table_ownership"
down_revision: str | None = "0004_sys_outbox_event_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建表归属登记表（含唯一约束与索引）。"""
    op.create_table(
        "sys_table_ownership",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("table_name", sa.String(length=64), nullable=False, comment="表名"),
        sa.Column("owner", sa.String(length=32), nullable=False, comment="归属服务标识（`*` = 每服务自有）"),
        sa.Column("datasource", sa.String(length=16), nullable=False, server_default="tenant", comment="库类别"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态"),
        sa.Column("note", sa.String(length=255), nullable=False, server_default="", comment="说明"),
        sa.UniqueConstraint("table_name", "deleted_at", name="uq_sys_table_ownership_name_deleted_at"),
    )
    op.create_index("idx_sys_table_ownership_deleted_at", "sys_table_ownership", ["deleted_at"])


def downgrade() -> None:
    """删除表归属登记表。"""
    op.drop_table("sys_table_ownership")
