"""发件箱 / 死信租户列改雪花 id（`tenant:tenant` 链 0003，10_04）。

Revision ID: 0003_sys_outbox_tenant_bigint
Revises: 0002_sys_outbox_event_version
Create Date: 2026-09-29

- 归属链：`tenant:tenant`（`tenant` 服务的租户库 `bms_tenant_{db_basis}`）；SQLite 经
  `batch_alter_table` 兼容（重建表）；
- 与 `platform/platform/0006_sys_outbox_tenant_bigint.py` 内容同构，仅 revision / 链不同；
- 存量行 `code → id` 回填由 `ops/backfill_tenant_id_columns.py` 在迁移前完成（结构与数据分离）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sys_outbox_tenant_bigint"
down_revision: str | None = "0002_sys_outbox_event_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """两表 `tenant_id` 由 `VARCHAR(64)` 改 `BIGINT`（可空保持）。"""
    for table in ("sys_outbox", "sys_event_dead_letter"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "tenant_id",
                existing_type=sa.String(length=64),
                type_=sa.BigInteger(),
                postgresql_using="tenant_id::bigint",
            )


def downgrade() -> None:
    """两表 `tenant_id` 改回 `VARCHAR(64)`。"""
    for table in ("sys_outbox", "sys_event_dead_letter"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "tenant_id",
                existing_type=sa.BigInteger(),
                type_=sa.String(length=64),
            )
