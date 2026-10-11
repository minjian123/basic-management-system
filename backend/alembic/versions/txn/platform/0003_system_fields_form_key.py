"""系统字段 `form_key` 落表（`txn:platform` 链 0003，02_11）。

Revision ID: 0003_system_fields_form_key
Revises: 0002_txn_outbox
Create Date: 2026-10-11

- 归属链：`txn:platform`（跨服务事务管理器 TM 账本库 `bms_txn`）；
- 口径：《数据库开发规范》「系统字段」节 §3.1.1（明细形态），需求 02-57，任务 02_11 详细设计；
- **明细表** `txn_global_branch` / `txn_global_recovery` 补 `parent_id`（上级明细 ID）；
  两表为账本 / 台账（无界面、不落 `form_key`）；
- 四库兼容：经 `batch_alter_table`（SQLite 重建表兼容）；只改结构不写种子。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_system_fields_form_key"
down_revision: str | None = "0002_txn_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

DETAIL_PARENT_COMMENT = "上级明细 ID（自引用同表 id；顶层 NULL）"

_TABLES: tuple[str, ...] = ("txn_global_branch", "txn_global_recovery")
"""本链明细表（补 parent_id）。"""


def upgrade() -> None:
    """`txn_global_branch` / `txn_global_recovery` 补 `parent_id`。"""
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("parent_id", sa.BigInteger(), nullable=True, comment=DETAIL_PARENT_COMMENT))


def downgrade() -> None:
    """回退：删 `parent_id`。"""
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("parent_id")
