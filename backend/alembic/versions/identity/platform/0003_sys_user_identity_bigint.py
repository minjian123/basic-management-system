"""身份映射租户列改雪花 id（`identity:platform` 链 0003，10_04）。

Revision ID: 0003_sys_user_identity_bigint
Revises: 0002_sys_outbox
Create Date: 2026-09-29

- 归属链：`identity:platform`（`identity` 服务的平台库 `bms_identity`）；SQLite 经
  `batch_alter_table` 兼容（重建表）；
- 列口径与 ORM 模型（`bms_identity/models/user_identity.py::SysUserIdentity`）逐项一致；
- 存量行 `code → id` 回填与 `idp_key` 前缀重写由 `ops/backfill_tenant_id_columns.py` 在迁移前完成
  （结构与数据分离；不可解析即中止）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sys_user_identity_bigint"
down_revision: str | None = "0002_sys_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """`sys_user_identity.tenant_id` 由 `VARCHAR(64)` 改 `BIGINT`（非空保持）。"""
    with op.batch_alter_table("sys_user_identity") as batch:
        batch.alter_column(
            "tenant_id",
            existing_type=sa.String(length=64),
            type_=sa.BigInteger(),
            postgresql_using="tenant_id::bigint",
        )


def downgrade() -> None:
    """`sys_user_identity.tenant_id` 改回 `VARCHAR(64)`。"""
    with op.batch_alter_table("sys_user_identity") as batch:
        batch.alter_column(
            "tenant_id",
            existing_type=sa.BigInteger(),
            type_=sa.String(length=64),
        )
