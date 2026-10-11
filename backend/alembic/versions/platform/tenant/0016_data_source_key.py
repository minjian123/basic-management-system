"""数据源归属列改按数据源标识（`platform:tenant` 链 0016，02_10）。

Revision ID: 0016_data_source_key
Revises: 0015_system_fields_form_key
Create Date: 2026-10-11

- 归属链：`platform:tenant`（`platform` 服务租户库 `bms_platform_{code}`）；
- 变更背景（`02_10` 统一数据源注册泛化）：字典数据源登记泛化为**统一数据源注册**，「字典标识」
  `dict_key` 泛化为**数据源标识** `data_source_key`（《命名规范》「标识用 `key`」；需求 02-57）——
  两表归属列随之改名：
  - `sys_data_scope.dict_key` → **`data_source_key`**（VARCHAR(64)，不可空）；
    唯一约束 **改名** `uq_sys_data_scope_role_dict_policy_deleted_at` →
    `uq_sys_data_scope_role_data_source_policy_deleted_at`（列集不变）；
  - `sys_query_scheme.dict_key` → **`data_source_key`**（VARCHAR(64)，可空）；
    唯一约束 `uq_scheme_scope_name_deleted_at` 含该列，随 `batch_alter_table` 重建表自动跟随（不显式删建）；
- **纯改名**：不改类型与可空性、不动数据、**无数据回填**（列语义不变，值仍为数据源标识业务码）；
- 四库兼容：经 `batch_alter_table` 的 `alter_column(new_column_name=...)` 与 `drop_constraint` /
  `create_unique_constraint`，不写方言 SQL。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_data_source_key"
down_revision: str | None = "0015_system_fields_form_key"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DATA_SCOPE_TABLE = "sys_data_scope"
"""数据权限表。"""

QUERY_SCHEME_TABLE = "sys_query_scheme"
"""查询方案表。"""

_OLD_DATA_SCOPE_CONSTRAINT = "uq_sys_data_scope_role_dict_policy_deleted_at"
"""数据权限表旧唯一约束名。"""

_NEW_DATA_SCOPE_CONSTRAINT = "uq_sys_data_scope_role_data_source_policy_deleted_at"
"""数据权限表新唯一约束名。"""

_DATA_SCOPE_CONSTRAINT_COLUMNS = ("role_id", "data_source_key", "policy_type", "deleted_at")
"""数据权限表唯一约束列（除首列改名外与旧口径一致）。"""


def upgrade() -> None:
    """两表归属列 `dict_key` → `data_source_key`（纯改名；数据权限表唯一约束同步更名）。"""
    with op.batch_alter_table(DATA_SCOPE_TABLE) as batch:
        batch.alter_column(
            "dict_key",
            new_column_name="data_source_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    with op.batch_alter_table(DATA_SCOPE_TABLE) as batch:
        batch.drop_constraint(_OLD_DATA_SCOPE_CONSTRAINT, type_="unique")
        batch.create_unique_constraint(_NEW_DATA_SCOPE_CONSTRAINT, list(_DATA_SCOPE_CONSTRAINT_COLUMNS))
    with op.batch_alter_table(QUERY_SCHEME_TABLE) as batch:
        batch.alter_column(
            "dict_key",
            new_column_name="data_source_key",
            existing_type=sa.String(length=64),
            nullable=True,
        )


def downgrade() -> None:
    """回退：两表归属列 `data_source_key` → `dict_key`（唯一约束名改回）。"""
    with op.batch_alter_table(QUERY_SCHEME_TABLE) as batch:
        batch.alter_column(
            "data_source_key",
            new_column_name="dict_key",
            existing_type=sa.String(length=64),
            nullable=True,
        )
    with op.batch_alter_table(DATA_SCOPE_TABLE) as batch:
        batch.drop_constraint(_NEW_DATA_SCOPE_CONSTRAINT, type_="unique")
        batch.create_unique_constraint(
            _OLD_DATA_SCOPE_CONSTRAINT,
            ["role_id", "data_source_key", "policy_type", "deleted_at"],
        )
    with op.batch_alter_table(DATA_SCOPE_TABLE) as batch:
        batch.alter_column(
            "data_source_key",
            new_column_name="dict_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
