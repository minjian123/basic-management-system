"""initial tenant tables

Revision ID: 0001
Revises:
Create Date: 2026-08-05

租户库初始表：sys_tenant_probe（阶段一验证表，软删除 + (唯一字段, deleted_at) 复合唯一索引演示）。
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
        "sys_tenant_probe",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False, comment="雪花 ID 主键"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="探测名称"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="软删除时间(UTC)"),
        sa.Column("version", sa.Integer(), nullable=False, comment="乐观锁版本"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间(UTC)"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人(用户ID)"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间(UTC)"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人(用户ID)"),
        sa.UniqueConstraint("name", "deleted_at", name="uq_tenant_probe_name"),
        comment="阶段一租户库验证表",
    )


def downgrade() -> None:
    op.drop_table("sys_tenant_probe")
