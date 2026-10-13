"""系统字段 `form_key` 落表（`platform:platform` 链 0010，02_11）。

Revision ID: 0010_system_fields_form_key
Revises: 0009_sys_product
Create Date: 2026-10-11

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- 口径：《数据库开发规范》「系统字段」节 §3.1.2 / §3.1.3 / §3.1.4，需求 02-57，任务 02_11 详细设计；
- **字典表**（`sys_module` / `sys_product` / `sys_business` / `sys_action`）补 `form_key`（表单标识，
  多表联合判别列）与 `parent_id`（上级字典 ID）；既有标识列 `module_key` / `product_key` **只改 DB 列名**
  为 `code`（ORM 属性与契约字段名保持），唯一约束同步更名；
- **明细表**（`sys_module_i18n` / `sys_business_i18n` / `sys_action_i18n` / `sys_menu_i18n` / `sys_field` /
  `sys_button` / `sys_field_i18n`）补 `parent_id`（上级明细 ID）；
- `form_key` 为每表常量（缺省取本表标识），加列即回填存量行；`(form_key, deleted_at)` 复合唯一；
- 四库兼容：经 `batch_alter_table`（SQLite 重建表兼容）；只改结构不写种子。
  列**改名**一律 `recreate="always"`：MySQL 的 `recreate="auto"` 会走 `ALTER ... CHANGE`，
  而 MySQL 要求 `CHANGE/MODIFY` 必须带类型（只给 `new_column_name` 即报
  `All MySQL CHANGE/MODIFY COLUMN operations require the existing type.`）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_system_fields_form_key"
down_revision: str | None = "0009_sys_product"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

FORM_KEY_COMMENT = "表单标识（多表联合判别列；全局唯一、保存后不变）"
DICT_PARENT_COMMENT = "上级字典 ID（自引用同表 id；顶层 NULL）"
DETAIL_PARENT_COMMENT = "上级明细 ID（自引用同表 id；顶层 NULL）"

_DICT_TABLES: tuple[tuple[str, str], ...] = (("sys_business", "business"), ("sys_action", "action"))
"""无改名的字典表（表名，form_key）。"""

_DETAIL_TABLES: tuple[str, ...] = (
    "sys_module_i18n",
    "sys_business_i18n",
    "sys_action_i18n",
    "sys_menu_i18n",
    "sys_field",
    "sys_button",
    "sys_field_i18n",
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


def _rename_identifier(table: str, old_name: str, new_name: str) -> None:
    """标识列 **只改 DB 列名**（ORM 属性与契约字段名保持）。

    Args:
        table: 表名。
        old_name: 原列名（ORM 属性名）。
        new_name: 新列名（DB 列名，`code`）。
    """
    with op.batch_alter_table(table, recreate="always") as batch:
        batch.alter_column(old_name, new_column_name=new_name)


def _rename_unique(table: str, old_name: str, new_name: str, columns: Sequence[str]) -> None:
    """同步唯一约束名（列随改名后的 DB 列名）。

    Args:
        table: 表名。
        old_name: 原约束名。
        new_name: 新约束名。
        columns: 约束列（DB 列名）。
    """
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(old_name, type_="unique")
        batch.create_unique_constraint(new_name, list(columns))


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
    _rename_identifier("sys_module", "module_key", "code")
    _rename_unique(
        "sys_module", "uq_sys_module_key_deleted_at", "uq_sys_module_code_deleted_at", ["code", "deleted_at"]
    )
    _add_dict_fields("sys_module", "module")

    _rename_identifier("sys_product", "product_key", "code")
    _rename_unique(
        "sys_product", "uq_sys_product_key_deleted_at", "uq_sys_product_code_deleted_at", ["code", "deleted_at"]
    )
    _add_dict_fields("sys_product", "product")

    for table, form_key in _DICT_TABLES:
        _add_dict_fields(table, form_key)

    for table in _DETAIL_TABLES:
        _add_parent_id(table)


def downgrade() -> None:
    """回退：删 `parent_id` / `form_key`（含唯一约束），标识列改回原名。"""
    for table in reversed(_DETAIL_TABLES):
        _drop_parent_id(table)

    for table, _form_key in reversed(_DICT_TABLES):
        _drop_dict_fields(table)

    _drop_dict_fields("sys_product")
    _rename_unique(
        "sys_product", "uq_sys_product_code_deleted_at", "uq_sys_product_key_deleted_at", ["product_key", "deleted_at"]
    )
    _rename_identifier("sys_product", "code", "product_key")

    _drop_dict_fields("sys_module")
    _rename_unique(
        "sys_module", "uq_sys_module_code_deleted_at", "uq_sys_module_key_deleted_at", ["module_key", "deleted_at"]
    )
    _rename_identifier("sys_module", "code", "module_key")
