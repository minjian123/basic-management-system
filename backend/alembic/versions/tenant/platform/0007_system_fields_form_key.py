"""系统字段 `form_key` 落表（`tenant:platform` 链 0007，02_11）。

Revision ID: 0007_system_fields_form_key
Revises: 0006_sys_user_tenant
Create Date: 2026-10-11

- 归属链：`tenant:platform`（`tenant` 服务的平台服务库 `bms_tenant`）；
- 口径：《数据库开发规范》「系统字段」节 §3.1.2 / §3.1.3 / §3.1.4，需求 02-57，任务 02_11 详细设计；
- **字典表** `sys_tenant` 补 `form_key`（表单标识，多表联合判别列）+ `parent_id`（上级字典 ID）+
  `(form_key, deleted_at)` 复合唯一；
- **明细表** `sys_tenant_database` 补 `parent_id`（上级明细 ID）；
- `form_key` 为每表常量（缺省取本表标识），加列即回填存量行；
- 四库兼容：经 `batch_alter_table`（SQLite 重建表兼容）；只改结构不写种子。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_system_fields_form_key"
down_revision: str | None = "0006_sys_user_tenant"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

FORM_KEY_COMMENT = "表单标识（多表联合判别列；全局唯一、保存后不变）"
DICT_PARENT_COMMENT = "上级字典 ID（自引用同表 id；顶层 NULL）"
DETAIL_PARENT_COMMENT = "上级明细 ID（自引用同表 id；顶层 NULL）"


def upgrade() -> None:
    """`sys_tenant` 补 `form_key` / `parent_id`；`sys_tenant_database` 补 `parent_id`。"""
    with op.batch_alter_table("sys_tenant") as batch:
        batch.add_column(
            sa.Column(
                "form_key",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'tenant'"),
                comment=FORM_KEY_COMMENT,
            )
        )
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DICT_PARENT_COMMENT))
        batch.create_unique_constraint("uq_sys_tenant_form_key_deleted_at", ["form_key", "deleted_at"])

    with op.batch_alter_table("sys_tenant_database") as batch:
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DETAIL_PARENT_COMMENT))


def downgrade() -> None:
    """回退：删 `parent_id`（两张表）与 `sys_tenant.form_key`（含唯一约束）。"""
    with op.batch_alter_table("sys_tenant_database") as batch:
        batch.drop_column("parent_id")
    with op.batch_alter_table("sys_tenant") as batch:
        batch.drop_constraint("uq_sys_tenant_form_key_deleted_at", type_="unique")
        batch.drop_column("parent_id")
        batch.drop_column("form_key")
