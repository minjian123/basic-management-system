"""查询方案归属列改按字典标识（`platform:tenant` 链 0014，02_09）。

Revision ID: 0014_query_scheme_dict_key
Revises: 0013_drop_dict_tables
Create Date: 2026-10-11

- 归属链：`platform:tenant`（`platform` 服务租户库）；
- 变更背景（`02_09` 口径返工）：查询方案表 `sys_query_scheme` 的字典归属列由 `dict_type` 改为
  **`dict_key`**（**字典标识**口径，与「标识用 `key`、代码用 `code`」一致；`target=items` 时填）；
- 唯一约束 `uq_scheme_scope_name_deleted_at` 含该列：随 `batch_alter_table` 重建表时按新列名自动跟随（不显式删建）；
- **纯改名**：不改类型与可空性、不动数据、**无数据回填**；
- 四库兼容：经 `batch_alter_table` 的 `alter_column(new_column_name=...)`，不写方言 SQL。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_query_scheme_dict_key"
down_revision: str | None = "0013_drop_dict_tables"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE = "sys_query_scheme"
"""查询方案表。"""


def upgrade() -> None:
    """`sys_query_scheme.dict_type` → `dict_key`（纯改名；重建表以兼容 MySQL 的改名口径）。"""
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        batch.alter_column("dict_type", new_column_name="dict_key")


def downgrade() -> None:
    """`dict_key` → `dict_type`（纯改名回退）。"""
    with op.batch_alter_table(TABLE, recreate="always") as batch:
        batch.alter_column("dict_key", new_column_name="dict_type")
