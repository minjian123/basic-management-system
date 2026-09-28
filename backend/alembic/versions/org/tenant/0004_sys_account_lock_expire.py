"""账号锁定记录补锁定期限与解锁方式字段（`org:tenant` 链，03_07）。

Revision ID: 0004_sys_account_lock_expire
Revises: 0003_sys_user_reset_contact
Create Date: 2026-09-28

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- `sys_account_lock` 新增可空 `expire_at`（锁定到期时间；`fail_limit` 有值、`inactive` / `manual` 为 NULL）与
  `unlock_mode`（解锁方式 manual / auto；NULL=未解锁）；
- 字段口径与 ORM 模型逐项一致（`bms_org/models/account_lock.py`）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_sys_account_lock_expire"
down_revision: str | None = "0003_sys_user_reset_contact"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """加 `sys_account_lock.expire_at` / `sys_account_lock.unlock_mode`（可空）。"""
    op.add_column(
        "sys_account_lock",
        sa.Column(
            "expire_at",
            sa.DateTime(),
            nullable=True,
            comment="锁定到期时间（UTC；NULL=需手动解锁）",
        ),
    )
    op.add_column(
        "sys_account_lock",
        sa.Column(
            "unlock_mode",
            sa.String(length=16),
            nullable=True,
            comment="解锁方式（manual/auto；NULL=未解锁）",
        ),
    )


def downgrade() -> None:
    """移除 `sys_account_lock.unlock_mode` / `sys_account_lock.expire_at`。"""
    op.drop_column("sys_account_lock", "unlock_mode")
    op.drop_column("sys_account_lock", "expire_at")
