"""会话记录表（`identity:tenant` 链首建，01_03）。

Revision ID: 0001_sys_session
Revises:
Create Date: 2026-09-26

- 归属链：`identity:tenant`（`identity` 服务的租户库 `bms_identity_{code}`）；
- 字段 / 索引口径与 ORM 模型（`bms_identity/models/session.py::SysSession`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；公共软删除索引 `idx_sys_session_deleted_at`；
- 只建表不写种子（登录运行时写入）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_sys_session"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("identity:tenant",)
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建会话记录表（含唯一约束与索引）。"""
    op.create_table(
        "sys_session",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID；= 会话 id）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("session_id", sa.String(length=64), nullable=False, comment="会话 id（= JWT jti；与 id 同值）"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户 ID（逻辑外键 → org 服务 sys_user.id）"),
        sa.Column(
            "refresh_token_hash", sa.String(length=128), nullable=False, comment="refresh token 哈希（SHA-256 hex）"
        ),
        sa.Column("device", sa.String(length=255), nullable=True, comment="设备标识（User-Agent 摘要）"),
        sa.Column("ip", sa.String(length=64), nullable=True, comment="登录 IP"),
        sa.Column("login_at", sa.DateTime(), nullable=False, comment="登录时间（UTC）"),
        sa.Column("expires_at", sa.DateTime(), nullable=False, comment="refresh 过期时间（UTC）"),
        sa.Column("revoked_at", sa.DateTime(), nullable=True, comment="撤销时间（UTC；NULL=有效）"),
        sa.UniqueConstraint("session_id", "deleted_at", name="uq_sys_session_session_id_deleted_at"),
    )
    op.create_index("idx_sys_session_deleted_at", "sys_session", ["deleted_at"])
    op.create_index("idx_sys_session_user_id", "sys_session", ["user_id"])


def downgrade() -> None:
    """删除会话记录表。"""
    op.drop_table("sys_session")
