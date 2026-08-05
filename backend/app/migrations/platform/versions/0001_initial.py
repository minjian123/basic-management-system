"""initial platform tables

Revision ID: 0001
Revises:
Create Date: 2026-08-05

平台库初始表：sys_migration_probe（阶段一验证表，验证双库路由与模型基类链路）。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | list[str] | None = None
depends_on: str | list[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_migration_probe",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False, comment="雪花 ID 主键"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="探测名称"),
        sa.Column("payload", sa.String(length=255), nullable=True, comment="附加载荷"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间(UTC)"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人(用户ID)"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间(UTC)"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人(用户ID)"),
        comment="阶段一平台库验证表",
    )


def downgrade() -> None:
    op.drop_table("sys_migration_probe")
