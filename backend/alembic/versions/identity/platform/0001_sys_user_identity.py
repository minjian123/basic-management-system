"""SSO 全局身份映射表（`identity:platform` 链首建，02_01）。

Revision ID: 0001_sys_user_identity
Revises:
Create Date: 2026-09-27

- 归属链：`identity:platform`（`identity` 服务的平台库 `bms_platform`，链首建）；
- 落平台库依据：SSO 回调在租户定位前即需按外部身份命中映射（需求 02-2 口径）；
- 字段 / 索引口径与 ORM 模型（`bms_identity/models/user_identity.py::SysUserIdentity`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；公共软删除索引 `idx_sys_user_identity_deleted_at`；
- 只建表不写种子（JIT 建号与映射写路径归 02_02）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_sys_user_identity"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("identity:platform",)
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建 SSO 全局身份映射表（含唯一约束与索引）。"""
    op.create_table(
        "sys_user_identity",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("idp_key", sa.String(length=160), nullable=False, comment="映射键（{tenant_code}:{provider_key}）"),
        sa.Column("external_id", sa.String(length=255), nullable=False, comment="外部身份主体（OIDC 取 sub）"),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, comment="租户编码（值传递）"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户 ID（逻辑外键 → org 服务 sys_user.id）"),
        sa.UniqueConstraint(
            "idp_key", "external_id", "deleted_at", name="uq_sys_user_identity_idp_external_deleted_at"
        ),
    )
    op.create_index("idx_sys_user_identity_deleted_at", "sys_user_identity", ["deleted_at"])
    op.create_index("idx_sys_user_identity_user_id", "sys_user_identity", ["user_id"])


def downgrade() -> None:
    """删除 SSO 全局身份映射表。"""
    op.drop_table("sys_user_identity")
