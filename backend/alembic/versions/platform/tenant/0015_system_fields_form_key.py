"""系统字段 `form_key` 落表（`platform:tenant` 链 0015，02_11）。

Revision ID: 0015_system_fields_form_key
Revises: 0014_query_scheme_dict_key
Create Date: 2026-10-11

- 归属链：`platform:tenant`（`platform` 服务租户库 `bms_platform_{code}`）；
- 口径：《数据库开发规范》「系统字段」节 §3.1.2 / §3.1.3 / §3.1.4，需求 02-57，任务 02_11 详细设计；
- **字典表**：`sys_role` 补 `form_key`（表单标识，多表联合判别列）+ `parent_id`（上级字典 ID）；
  `sys_user` / `sys_config` 另把既有标识列（`username` / `config_key`）**只改 DB 列名**为 `code`
  （ORM 属性与契约字段名保持），唯一约束同步更名；`sys_config` 补 `name` / `status`；
- **明细表**（`sys_account_lock` / `sys_role_permission` / `sys_role_field` / `sys_data_scope` /
  `sys_user_extension`）补 `parent_id`（上级明细 ID）；
- `form_key` 为每表常量（缺省取本表标识），加列即回填存量行；`(form_key, deleted_at)` 复合唯一；
- 四库兼容：经 `batch_alter_table`（SQLite 重建表兼容）；只改结构不写种子。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_system_fields_form_key"
down_revision: str | None = "0014_query_scheme_dict_key"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

FORM_KEY_COMMENT = "表单标识（多表联合判别列；全局唯一、保存后不变）"
DICT_PARENT_COMMENT = "上级字典 ID（自引用同表 id；顶层 NULL）"
DETAIL_PARENT_COMMENT = "上级明细 ID（自引用同表 id；顶层 NULL）"

_DETAIL_TABLES: tuple[str, ...] = (
    "sys_account_lock",
    "sys_role_permission",
    "sys_role_field",
    "sys_data_scope",
    "sys_user_extension",
)
"""本链明细表（补 parent_id）。"""


def _add_dict_fields(table: str, form_key: str) -> None:
    """字典表：加 `form_key`（常量缺省）+ `parent_id` + `(form_key, deleted_at)` 唯一约束。

    Args:
        table: 表名。
        form_key: 本表表单标识（每表常量）。
    """
    with op.batch_alter_table(table) as batch:
        batch.add_column(
            sa.Column(
                "form_key",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text(f"'{form_key}'"),
                comment=FORM_KEY_COMMENT,
            )
        )
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DICT_PARENT_COMMENT))
        batch.create_unique_constraint(f"uq_{table}_form_key_deleted_at", ["form_key", "deleted_at"])


def _drop_dict_fields(table: str) -> None:
    """反演 `_add_dict_fields`。

    Args:
        table: 表名。
    """
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(f"uq_{table}_form_key_deleted_at", type_="unique")
        batch.drop_column("parent_id")
        batch.drop_column("form_key")


def _add_parent_id(table: str) -> None:
    """明细表：加 `parent_id`（上级明细 ID）。

    Args:
        table: 表名。
    """
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DETAIL_PARENT_COMMENT))


def _drop_parent_id(table: str) -> None:
    """反演 `_add_parent_id`。

    Args:
        table: 表名。
    """
    with op.batch_alter_table(table) as batch:
        batch.drop_column("parent_id")


def upgrade() -> None:
    """补 `form_key` / `parent_id`（字典表）与 `parent_id`（明细表），并同步标识列改名。"""
    _add_dict_fields("sys_role", "role")

    # sys_user：username → code（只改 DB 列名）+ form_key + parent_id
    with op.batch_alter_table("sys_user") as batch:
        batch.alter_column("username", new_column_name="code")
    with op.batch_alter_table("sys_user") as batch:
        batch.drop_constraint("uq_sys_user_username_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_user_code_deleted_at", ["code", "deleted_at"])
    _add_dict_fields("sys_user", "user")

    # sys_config：config_key → code（只改 DB 列名）+ form_key + name + status + parent_id
    with op.batch_alter_table("sys_config") as batch:
        batch.alter_column("config_key", new_column_name="code")
    with op.batch_alter_table("sys_config") as batch:
        batch.drop_constraint("uq_sys_config_config_key_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_config_code_deleted_at", ["code", "deleted_at"])
    with op.batch_alter_table("sys_config") as batch:
        batch.add_column(
            sa.Column(
                "name", sa.String(length=128), nullable=False, server_default=sa.text("''"), comment="参数名称（展示）"
            )
        )
        batch.add_column(
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'enabled'"),
                comment="状态（enabled/disabled）",
            )
        )
    _add_dict_fields("sys_config", "config")

    for table in _DETAIL_TABLES:
        _add_parent_id(table)


def downgrade() -> None:
    """回退：删 `parent_id` / `form_key`（含唯一约束）与 `sys_config.name` / `status`，标识列改回原名。"""
    for table in reversed(_DETAIL_TABLES):
        _drop_parent_id(table)

    _drop_dict_fields("sys_config")
    with op.batch_alter_table("sys_config") as batch:
        batch.drop_column("status")
        batch.drop_column("name")
    with op.batch_alter_table("sys_config") as batch:
        batch.drop_constraint("uq_sys_config_code_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_config_config_key_deleted_at", ["config_key", "deleted_at"])
    with op.batch_alter_table("sys_config") as batch:
        batch.alter_column("code", new_column_name="config_key")

    _drop_dict_fields("sys_user")
    with op.batch_alter_table("sys_user") as batch:
        batch.drop_constraint("uq_sys_user_code_deleted_at", type_="unique")
        batch.create_unique_constraint("uq_sys_user_username_deleted_at", ["username", "deleted_at"])
    with op.batch_alter_table("sys_user") as batch:
        batch.alter_column("code", new_column_name="username")

    _drop_dict_fields("sys_role")
