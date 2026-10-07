"""删用户与账号锁定两表（`org:tenant` 链，02_05）。

Revision ID: 0006_drop_user_tables
Revises: 0005_sys_outbox
Create Date: 2026-10-07

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- 迁移背景（需求 07-10 用户（账号）归口平台）：`sys_user` / `sys_account_lock` 归属改
  **platform 服务租户库**（platform 链 `0008_user_tables` 建表）；本迁移删除 org 侧两表，
  使 `org:tenant` 链**净零**（历史建表 `0001~0004` + 本次删表），已部署库链保持连续不破；
- **迁移执行顺序（已部署环境·强制）**：platform 链 `0008_user_tables`（建表）→
  `ops.migrate_user_tables`（跨库数据搬迁）→ 本迁移（删表）；顺序颠倒会丢数据；
  本地开发库直接重建，不走搬迁脚本；
- `downgrade()` 按 org 链 `0001~0004` 的最终结构**复原**两表（保证链可回滚）；
- org 服务此后不再持有用户 / 账号锁定模型（`bms_org/models/__init__.py` 收敛为空元组）。
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0006_drop_user_tables"
down_revision: str | None = "0005_sys_outbox"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _common_columns() -> tuple[sa.Column[Any], ...]:
    """公共字段（对齐 `BaseModel`；复原两表用，每次调用返回新实例）。

    Returns:
        tuple[sa.Column[Any], ...]: 公共列定义。
    """
    return (
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
    )


def upgrade() -> None:
    """删 `sys_account_lock` 与 `sys_user`（逆序；表已迁 platform 服务租户库）。"""
    op.drop_table("sys_account_lock")
    op.drop_table("sys_user")


def downgrade() -> None:
    """按最终结构复原两表（`sys_user` → `sys_account_lock`）。"""
    op.create_table(
        "sys_user",
        *_common_columns(),
        sa.Column("username", sa.String(length=64), nullable=False, comment="登录账号（唯一；软删除后可复用）"),
        sa.Column("password_hash", sa.String(length=255), nullable=False, comment="口令哈希（PBKDF2 自描述串）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="用户昵称 / 显示名"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（enabled/disabled）"),
        sa.Column(
            "failed_count", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="连续登录失败次数"
        ),
        sa.Column("locked_until", sa.DateTime(), nullable=True, comment="锁定到期时间（UTC；NULL=未锁）"),
        sa.Column("pwd_changed_at", sa.DateTime(), nullable=True, comment="密码最近变更时间（UTC）"),
        sa.Column("pwd_history", sa.Text(), nullable=True, comment="历史密码哈希（JSON 数组，仅应用侧读写）"),
        sa.Column(
            "pwd_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否需强制改密（登录超期置真，改密成功清假）",
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True, comment="最近登录时间（UTC）"),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
            comment="邮箱（找回密码通道；维护入口归用户管理阶段）",
        ),
        sa.Column(
            "phone",
            sa.String(length=32),
            nullable=True,
            comment="手机号（找回密码通道；维护入口归用户管理阶段）",
        ),
        sa.Column("locale", sa.String(length=16), nullable=True, comment="语言偏好（如 zh-cn）"),
        sa.Column("timezone", sa.String(length=64), nullable=True, comment="时区偏好（如 Asia/Shanghai）"),
        sa.UniqueConstraint("username", "deleted_at", name="uq_sys_user_username_deleted_at"),
    )
    op.create_index("idx_sys_user_deleted_at", "sys_user", ["deleted_at"])

    op.create_table(
        "sys_account_lock",
        *_common_columns(),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户主键（逻辑外键 sys_user.id）"),
        sa.Column("lock_type", sa.String(length=16), nullable=False, comment="锁定类型（fail_limit/inactive/manual）"),
        sa.Column("reason", sa.String(length=255), nullable=True, comment="锁定原因"),
        sa.Column("locked_at", sa.DateTime(), nullable=False, comment="锁定时间（UTC）"),
        sa.Column("locked_by", sa.BigInteger(), nullable=True, comment="锁定操作人（inactive / 系统触发为 NULL）"),
        sa.Column("expire_at", sa.DateTime(), nullable=True, comment="锁定到期时间（UTC；NULL=需手动解锁）"),
        sa.Column("unlock_at", sa.DateTime(), nullable=True, comment="解锁时间（UTC；NULL=未解锁）"),
        sa.Column("unlock_by", sa.BigInteger(), nullable=True, comment="解锁操作人（NULL=未解锁）"),
        sa.Column("unlock_mode", sa.String(length=16), nullable=True, comment="解锁方式（manual/auto；NULL=未解锁）"),
    )
    op.create_index("idx_sys_account_lock_deleted_at", "sys_account_lock", ["deleted_at"])
    op.create_index("idx_sys_account_lock_user_locked", "sys_account_lock", ["user_id", "locked_at"])
    op.create_index("idx_sys_account_lock_user_unlock", "sys_account_lock", ["user_id", "unlock_at"])
    op.create_index("idx_sys_account_lock_unlock_by", "sys_account_lock", ["unlock_by"])
