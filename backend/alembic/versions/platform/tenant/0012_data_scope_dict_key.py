"""数据权限归属改按字典标识（`platform:tenant` 链 0012，02_09）。

Revision ID: 0012_data_scope_dict_key
Revises: 0011_dict_field_names
Create Date: 2026-10-11

- 归属链：`platform:tenant`（`platform` 服务租户库）；
- 变更背景（`02_09` 口径返工）：`sys_data_scope` 归属列由 `dict_type_id`（BIGINT → 字典类型主键）改为
  **`dict_key` VARCHAR(64)**（**字典标识业务码字符串**，如 `role` / `org_dept` / `wms_bin`；不再指向
  已拆除的 `sys_dict_type`）；
- **存量清理**：字典域废弃，存量行**清空不回填**（`DELETE` 后改列）；
- 唯一约束 `uq_sys_data_scope_role_dict_policy_deleted_at` 列随改名（`dict_type_id` → `dict_key`），约束名不变；
- 四库兼容：`batch_alter_table` + `existing_type`，不写方言 SQL；
- `downgrade` 反向改回 `dict_type_id`（BIGINT，存量不回填）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_data_scope_dict_key"
down_revision: str | None = "0011_dict_field_names"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE = "sys_data_scope"
"""数据权限表。"""


def upgrade() -> None:
    """`sys_data_scope.dict_type_id` → `dict_key` VARCHAR(64)（存量清空）。"""
    op.execute(f"DELETE FROM {TABLE}")
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(
            "dict_type_id",
            new_column_name="dict_key",
            type_=sa.String(length=64),
            existing_type=sa.BigInteger(),
            nullable=False,
        )


def downgrade() -> None:
    """`dict_key` → `dict_type_id` BIGINT（存量不回填）。"""
    op.execute(f"DELETE FROM {TABLE}")
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(
            "dict_key",
            new_column_name="dict_type_id",
            type_=sa.BigInteger(),
            existing_type=sa.String(length=64),
            nullable=False,
        )
