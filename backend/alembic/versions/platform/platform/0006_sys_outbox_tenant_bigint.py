"""发件箱 / 死信租户列改雪花 id（`platform:platform` 链 0006，10_04）。

Revision ID: 0006_sys_outbox_tenant_bigint
Revises: 0005_sys_table_ownership
Create Date: 2026-09-29

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；SQLite 经
  `batch_alter_table` 兼容（重建表）；
- 列口径与 ORM 模型（`bms_core/models/outbox.py::SysOutbox` / `SysEventDeadLetter`）逐项一致；
- 存量行 `code → id` 回填由 `ops/backfill_tenant_id_columns.py` 在迁移前完成（结构与数据分离）；
- 其余链同构脚本见 `platform/tenant/0005_sys_outbox_tenant_bigint.py`、
  `tenant/platform/0005_sys_outbox_tenant_bigint.py`、`tenant/tenant/0003_sys_outbox_tenant_bigint.py`。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_sys_outbox_tenant_bigint"
down_revision: str | None = "0005_sys_table_ownership"
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
