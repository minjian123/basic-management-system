"""租户外部 IdP 配置表（`identity:tenant` 链 0002，02_01）。

Revision ID: 0002_sys_identity_provider
Revises: 0001_sys_session
Create Date: 2026-09-27

- 归属链：`identity:tenant`（`identity` 服务的租户库 `bms_identity_{code}`）；
- 字段 / 索引口径与 ORM 模型（`bms_identity/models/identity_provider.py::SysIdentityProvider`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；公共软删除索引 `idx_sys_identity_provider_deleted_at`；
- 只建表不写种子（dev 种子由 `ops/seed_sso.py` 显式执行）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_sys_identity_provider"
down_revision: str | None = "0001_sys_session"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建租户外部 IdP 配置表（含唯一约束与索引）。"""
    op.create_table(
        "sys_identity_provider",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="显示名（登录页入口文案）"),
        sa.Column("idp_key", sa.String(length=64), nullable=False, comment="租户内稳定标识 slug（路由参数）"),
        sa.Column("type", sa.String(length=32), nullable=False, comment="协议类型（oidc/cas/wecom/dingtalk）"),
        sa.Column("icon", sa.String(length=255), nullable=True, comment="图标（空回退默认样式）"),
        sa.Column("config", sa.Text(), nullable=False, comment="协议配置 JSON（密钥类只存引用）"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="登录页排序（升序）"),
        sa.UniqueConstraint("idp_key", "deleted_at", name="uq_sys_identity_provider_idp_key_deleted_at"),
    )
    op.create_index("idx_sys_identity_provider_deleted_at", "sys_identity_provider", ["deleted_at"])
    op.create_index("idx_sys_identity_provider_status_sort", "sys_identity_provider", ["status", "sort"])


def downgrade() -> None:
    """删除租户外部 IdP 配置表。"""
    op.drop_table("sys_identity_provider")
