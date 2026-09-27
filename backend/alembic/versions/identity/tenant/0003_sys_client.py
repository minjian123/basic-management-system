"""第三方应用客户端表（`identity:tenant` 链 0003，02_05）。

Revision ID: 0003_sys_client
Revises: 0002_sys_identity_provider
Create Date: 2026-09-27

- 归属链：`identity:tenant`（`identity` 服务的租户库 `bms_identity_{code}`）；
- 字段 / 索引口径与 ORM 模型（`bms_identity/models/client.py::SysClient`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；公共软删除索引 `idx_sys_client_deleted_at`；
- 只建表不写种子（dev 测试客户端由 `ops/seed_oidc_client.py` 显式执行）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_sys_client"
down_revision: str | None = "0002_sys_identity_provider"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建第三方应用客户端表（含唯一约束与索引）。"""
    op.create_table(
        "sys_client",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("client_id", sa.String(length=64), nullable=False, comment="客户端标识（租户内唯一）"),
        sa.Column(
            "client_secret_hash", sa.String(length=255), nullable=True, comment="客户端密钥哈希（公共客户端为空）"
        ),
        sa.Column("name", sa.String(length=128), nullable=False, comment="应用名称（管理展示）"),
        sa.Column("redirect_uris", sa.Text(), nullable=False, comment="回调地址白名单 JSON 数组"),
        sa.Column("grant_types", sa.Text(), nullable=False, comment="授权类型 JSON 数组"),
        sa.Column("scopes", sa.Text(), nullable=False, comment="scope 集合 JSON 数组"),
        sa.Column(
            "ip_whitelist", sa.Text(), nullable=False, comment="IP / CIDR 白名单 JSON 数组（默认值由应用侧写 []）"
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="enabled", comment="状态"),
        sa.UniqueConstraint("client_id", "deleted_at", name="uq_sys_client_client_id_deleted_at"),
    )
    op.create_index("idx_sys_client_deleted_at", "sys_client", ["deleted_at"])


def downgrade() -> None:
    """删除第三方应用客户端表。"""
    op.drop_table("sys_client")
