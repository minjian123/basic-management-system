"""用户最小模型表（`org:tenant` 链首建，01_03）。

Revision ID: 0001_sys_user
Revises:
Create Date: 2026-09-26

- 归属链：`org:tenant`（`org` 服务的租户库 `bms_org_{code}`）；
- 字段 / 索引口径与 ORM 模型（`bms_org/models/user.py::SysUser`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；公共软删除索引 `idx_sys_user_deleted_at`；
- 只建表不写种子（初始系统管理员种子归租户开通阶段）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_sys_user"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("org:tenant",)
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建用户最小模型表（含唯一约束与索引）。"""
    op.create_table(
        "sys_user",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
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
        sa.Column("last_login_at", sa.DateTime(), nullable=True, comment="最近登录时间（UTC）"),
        sa.Column("locale", sa.String(length=16), nullable=True, comment="语言偏好（如 zh-cn）"),
        sa.Column("timezone", sa.String(length=64), nullable=True, comment="时区偏好（如 Asia/Shanghai）"),
        sa.UniqueConstraint("username", "deleted_at", name="uq_sys_user_username_deleted_at"),
    )
    op.create_index("idx_sys_user_deleted_at", "sys_user", ["deleted_at"])


def downgrade() -> None:
    """删除用户最小模型表。"""
    op.drop_table("sys_user")
