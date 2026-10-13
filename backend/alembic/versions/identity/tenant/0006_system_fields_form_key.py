"""系统字段 `form_key` 落表（`identity:tenant` 链 0006，02_11）。

Revision ID: 0006_system_fields_form_key
Revises: 0005_sys_session_remember_me
Create Date: 2026-10-11

- 归属链：`identity:tenant`（`identity` 服务租户库 `bms_identity_{code}`）；
- 口径：《数据库开发规范》「系统字段」节 §3.1.2 / §3.1.3 / §3.1.4，需求 02-57，任务 02_11 详细设计；
- **字典表** `sys_identity_provider` / `sys_client` 补 `form_key`（表单标识，多表联合判别列）+
  `parent_id`（上级字典 ID）+ `(form_key, deleted_at)` 复合唯一；既有标识列 `idp_key` / `client_id`
  **只改 DB 列名**为 `code`（ORM 属性与契约字段名保持），唯一约束同步更名；
- `form_key` 为每表常量（缺省取本表标识），加列即回填存量行；
- 四库兼容：经 `batch_alter_table`（SQLite 重建表兼容）；只改结构不写种子。
  列**改名**一律 `recreate="always"`（MySQL 的 `recreate="auto"` 走 `ALTER ... CHANGE`，
  而 MySQL 要求 `CHANGE/MODIFY` 必须带类型，只给 `new_column_name` 即报错）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_system_fields_form_key"
down_revision: str | None = "0005_sys_session_remember_me"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

FORM_KEY_COMMENT = "表单标识（多表联合判别列；全局唯一、保存后不变）"
DICT_PARENT_COMMENT = "上级字典 ID（自引用同表 id；顶层 NULL）"


def upgrade() -> None:
    """`sys_identity_provider` / `sys_client`：标识列改 `code` + 补 `form_key` / `parent_id`。"""
    with op.batch_alter_table("sys_identity_provider", recreate="always") as batch:
        batch.alter_column("idp_key", new_column_name="code")
    with op.batch_alter_table("sys_identity_provider") as batch:
        batch.drop_constraint("uq_sys_identity_provider_idp_key_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_identity_provider_code_deleted_at", ["code", "deleted_at"])
        batch.add_column(
            sa.Column(
                "form_key",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'identity_provider'"),
                comment=FORM_KEY_COMMENT,
            )
        )
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DICT_PARENT_COMMENT))
        batch.create_unique_constraint("uq_sys_identity_provider_form_key_deleted_at", ["form_key", "deleted_at"])

    with op.batch_alter_table("sys_client", recreate="always") as batch:
        batch.alter_column("client_id", new_column_name="code")
    with op.batch_alter_table("sys_client") as batch:
        batch.drop_constraint("uq_sys_client_client_id_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_client_code_deleted_at", ["code", "deleted_at"])
        batch.add_column(
            sa.Column(
                "form_key",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'client'"),
                comment=FORM_KEY_COMMENT,
            )
        )
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DICT_PARENT_COMMENT))
        batch.create_unique_constraint("uq_sys_client_form_key_deleted_at", ["form_key", "deleted_at"])


def downgrade() -> None:
    """回退：删 `form_key` / `parent_id`（含唯一约束），标识列改回原名。"""
    with op.batch_alter_table("sys_client") as batch:
        batch.drop_constraint("uq_sys_client_form_key_deleted_at", type_="unique")
        batch.drop_constraint("uq_sys_client_code_deleted_at", type_="unique")
        batch.drop_column("parent_id")
        batch.drop_column("form_key")
        batch.create_unique_constraint("uq_sys_client_client_id_deleted_at", ["client_id", "deleted_at"])
    with op.batch_alter_table("sys_client", recreate="always") as batch:
        batch.alter_column("code", new_column_name="client_id")

    with op.batch_alter_table("sys_identity_provider") as batch:
        batch.drop_constraint("uq_sys_identity_provider_form_key_deleted_at", type_="unique")
        batch.drop_constraint("uq_sys_identity_provider_code_deleted_at", type_="unique")
        batch.drop_column("parent_id")
        batch.drop_column("form_key")
        batch.create_unique_constraint("uq_sys_identity_provider_idp_key_deleted_at", ["idp_key", "deleted_at"])
    with op.batch_alter_table("sys_identity_provider", recreate="always") as batch:
        batch.alter_column("code", new_column_name="idp_key")
