"""字典条目上级 ID 改雪花 id（`platform:tenant` 链 0010，02_07）。

Revision ID: 0010_dict_item_parent_id_bigint
Revises: 0009_role_type
Create Date: 2026-10-10

- 归属链：`platform:tenant`（`platform` 服务的租户库 `bms_platform_{db_basis}`；字典六表与之同库）；
  SQLite 经 `batch_alter_table` 兼容（重建表）；
- 迁移背景（`02_07` 字典系统字段口径收口）：`sys_dict_item.parent_id` 由「引用父条目 `value`（`VARCHAR(64)`）」
  改为「**上级条目 ID**（`BIGINT`，自引用同表 `id`）」，与《概要设计 · 字典管理》「核心表」节及
  《数据库开发规范》「系统字段」节一致；
- 存量行 `父 value → 父 id` 回填由 `ops.backfill_dict_parent_id` **在迁移前**完成（结构与数据分离）——
  规避 `VARCHAR` → `BIGINT` 在 MySQL / PostgreSQL / 达梦下对非数字值的截断与报错；
- 可空性保持（顶层为 `NULL`）；索引 `idx_dict_item_parent_sort` 随列类型变更；
- 四库兼容：经 `batch_alter_table` 只改类型，PostgreSQL 走 `postgresql_using`（不写方言 SQL、不用方言专用类型）；
- `downgrade`：改回 `VARCHAR(64)`（整型值将变为十进制字符串；语义回退到「父 value」需另跑反向回填）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_dict_item_parent_id_bigint"
down_revision: str | None = "0009_role_type"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE = "sys_dict_item"
"""目标表名。"""

COLUMN = "parent_id"
"""目标列名（上级条目 ID）。"""


def upgrade() -> None:
    """`sys_dict_item.parent_id` 由 `VARCHAR(64)` 改 `BIGINT`（可空保持）。"""
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(
            COLUMN,
            existing_type=sa.String(length=64),
            type_=sa.BigInteger(),
            postgresql_using="parent_id::bigint",
        )


def downgrade() -> None:
    """`sys_dict_item.parent_id` 改回 `VARCHAR(64)`。"""
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column(
            COLUMN,
            existing_type=sa.BigInteger(),
            type_=sa.String(length=64),
        )
