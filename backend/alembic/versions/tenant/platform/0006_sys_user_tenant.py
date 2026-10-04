"""用户↔租户可达关系表（`tenant:platform` 链 0006，11_01）：新建 sys_user_tenant。

Revision ID: 0006_sys_user_tenant
Revises: 0005_sys_outbox_tenant_bigint
Create Date: 2026-10-04

- 归属链：`tenant:platform`（`tenant` 服务的平台服务库 `bms_tenant`，与 `sys_tenant` 同库）；
- 语义：一行 = 某租户（归属租户 `tenant_id`）内某用户（`user_id`）可访问目标租户
  （`target_tenant_id`）；每个用户恒有一行指向其归属租户自身（自有租户）；
- 字段 / 索引口径与 ORM 模型（`bms_tenant/models/user_tenant.py::SysUserTenant`）逐项一致；
- 复合唯一 `(tenant_id, user_id, target_tenant_id, deleted_at)`（软删后可重挂），其前缀
  `(tenant_id, user_id)` 覆盖读路径主查询，不另建普通索引；
- 只建表不写种子（关系随建号 / 回收路径由租户服务内部端点维护）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_sys_user_tenant"
down_revision: str | None = "0005_sys_outbox_tenant_bigint"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建用户↔租户可达关系表（含唯一约束与软删除索引）。"""
    op.create_table(
        "sys_user_tenant",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column(
            "tenant_id", sa.BigInteger(), nullable=False, comment="归属租户主键（同库逻辑外键 → sys_tenant.id，只持值）"
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            nullable=False,
            comment="用户主键（跨服务逻辑外键 → org 服务 sys_user.id，只持值）",
        ),
        sa.Column(
            "target_tenant_id",
            sa.BigInteger(),
            nullable=False,
            comment="可访问目标租户主键（同库逻辑外键 → sys_tenant.id，只持值）",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            comment="写入来源（super_admin / admin_create / import / sso_jit / self_register / self_heal）",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="状态（active / disabled；回收置 disabled，彻底移除才软删）",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "user_id",
            "target_tenant_id",
            "deleted_at",
            name="uq_sys_user_tenant_tenant_user_target_deleted_at",
        ),
    )
    op.create_index("idx_sys_user_tenant_deleted_at", "sys_user_tenant", ["deleted_at"])


def downgrade() -> None:
    """删除用户↔租户可达关系表。"""
    op.drop_table("sys_user_tenant")
