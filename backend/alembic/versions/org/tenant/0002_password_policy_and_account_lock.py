"""密码策略字段与账号锁定表（`org:tenant` 链，03_05）。

Revision ID: 0002_password_policy_and_account_lock
Revises: 0001_sys_user
Create Date: 2026-09-27

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- `sys_user` 新增 `pwd_reset_required`（强制改密标志；Boolean 跨方言，`server_default=sa.false()`）；
- 新建 `sys_account_lock`（账号锁定记录；`inactive` 由 03_05 写入，两型与解锁归 03_07）；
- 字段 / 索引口径与 ORM 模型逐项一致（`bms_org/models/user.py` / `bms_org/models/account_lock.py`）；
- 公共字段对齐 `BaseModel`；软删除索引 `idx_sys_account_lock_deleted_at` 由命名约定生成、此处显式建。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_password_policy_and_account_lock"
down_revision: str | None = "0001_sys_user"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """加 `sys_user.pwd_reset_required` 并建 `sys_account_lock` 表（含索引）。"""
    op.add_column(
        "sys_user",
        sa.Column(
            "pwd_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否需强制改密（登录超期置真，改密成功清假）",
        ),
    )
    op.create_table(
        "sys_account_lock",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户主键（逻辑外键 sys_user.id）"),
        sa.Column("lock_type", sa.String(length=16), nullable=False, comment="锁定类型（fail_limit/inactive/manual）"),
        sa.Column("reason", sa.String(length=255), nullable=True, comment="锁定原因"),
        sa.Column("locked_at", sa.DateTime(), nullable=False, comment="锁定时间（UTC）"),
        sa.Column("locked_by", sa.BigInteger(), nullable=True, comment="锁定操作人（inactive / 系统触发为 NULL）"),
        sa.Column("unlock_at", sa.DateTime(), nullable=True, comment="解锁时间（UTC；NULL=未解锁）"),
        sa.Column("unlock_by", sa.BigInteger(), nullable=True, comment="解锁操作人（NULL=未解锁）"),
    )
    op.create_index("idx_sys_account_lock_deleted_at", "sys_account_lock", ["deleted_at"])
    op.create_index("idx_sys_account_lock_user_locked", "sys_account_lock", ["user_id", "locked_at"])
    op.create_index("idx_sys_account_lock_user_unlock", "sys_account_lock", ["user_id", "unlock_at"])
    op.create_index("idx_sys_account_lock_unlock_by", "sys_account_lock", ["unlock_by"])


def downgrade() -> None:
    """删除 `sys_account_lock` 表并移除 `sys_user.pwd_reset_required`。"""
    op.drop_table("sys_account_lock")
    op.drop_column("sys_user", "pwd_reset_required")
