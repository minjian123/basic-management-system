"""租户注册数据源键列改可空（平台链 0005，06_01）：sys_tenant.db_key 废弃。

Revision ID: 0005_sys_tenant_db_key_nullable
Revises: 0004_sys_outbox_event_version
Create Date: 2026-09-23

- 归属链：`platform`（平台数据源）；SQLite 经 `batch_alter_table` 兼容（重建表），四库通用；
- `sys_tenant.db_key` 由 `NOT NULL` 改为**可空**：06_01 起注册表**不再写入**该列——服务化后
  租户库键一律由 `tenant_{service}_{code}` 派生（见 `bms_core/db/keys.py`），注册表不再持有数据源键；
- 存量取值保留（不再被消费）；**物理删列另立任务**（数据库治理）；
- 列注释差异：真库列注释随下次列变更迁移同步（SQLite 无注释语义，故本迁移不写注释）；
- 表结构以《数据库设计》数据表文件 `sys_tenant.md` 为唯一事实源。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_sys_tenant_db_key_nullable"
down_revision: str | None = "0004_sys_outbox_event_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """`sys_tenant.db_key` 改可空（废弃列，不再写入）。"""
    with op.batch_alter_table("sys_tenant") as batch:
        batch.alter_column("db_key", existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    """恢复非空约束（`NULL` 存量行先回填空串以满足约束）。"""
    op.execute("UPDATE sys_tenant SET db_key = '' WHERE db_key IS NULL")
    with op.batch_alter_table("sys_tenant") as batch:
        batch.alter_column("db_key", existing_type=sa.String(length=64), nullable=False)
