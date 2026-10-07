"""用户与账号锁定两表（`platform:tenant` 链，02_05）。

Revision ID: 0008_user_tables
Revises: 0007_role_tables
Create Date: 2026-10-07

- 归属链：`platform:tenant`（platform 服务租户库 `bms_platform_{code}`，与角色 / 授权、字典 / 系统参数同库）；
- 迁移背景（需求 07-10 用户（账号）归口平台）：`sys_user` / `sys_account_lock` 由 org 服务租户库迁入，
  使「用户 / 角色 / 授权」同服务同库、消除跨服务引用（`sys_user_role.user_id` 由跨服务降为同库引用）；
- 结构取 org 链 `0001~0004` 的**最终形态**（含 `pwd_reset_required` / `email` / `phone` /
  `expire_at` / `unlock_mode`），字段 / 唯一约束 / 业务索引 / 软删除索引与 ORM 模型
  （`bms_platform/models/user.py`）逐项一致；
- 与 org 链的关系：`org:tenant` 链 `0001~0005` **原样保留**（已部署库链不破），
  org 侧另由 `0006_drop_user_tables` 删表收敛为净零；
- **迁移执行顺序（已部署环境·强制）**：先跑本迁移建表 → 再跑 `ops.migrate_user_tables` 搬数据 →
  最后跑 `org:tenant` 的 `0006_drop_user_tables` 删表；顺序颠倒会丢数据；
- 公共字段对齐 `BaseModel`；公共软删除索引显式建；
- 只建表不写种子（初始系统管理员由 `ops/seed_user.py` 负责）。
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0008_user_tables"
down_revision: str | None = "0007_role_tables"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _common_columns() -> tuple[sa.Column[Any], ...]:
    """公共字段（对齐 `BaseModel`；每次调用返回新实例，供多表建表复用）。

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
    """建 `sys_user` / `sys_account_lock`（含唯一约束、业务索引与软删除索引）。"""
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
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户主键（逻辑外键 sys_user.id；同库）"),
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


def downgrade() -> None:
    """删除 `sys_account_lock` 与 `sys_user`（逆序）。"""
    op.drop_table("sys_account_lock")
    op.drop_table("sys_user")
