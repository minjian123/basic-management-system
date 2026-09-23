"""租户注册表（`tenant:platform` 链首建，06_02 分链）。

Revision ID: 0001_sys_tenant
Revises:
Create Date: 2026-09-23

- 归属链：`tenant:platform`（`tenant` 服务的平台服务库 `bms_tenant`）；
- **由原 `versions/platform/0001_sys_tenant_module.py` 按表归属拆分**而来；`sys_tenant.db_key` 直接
  建为**可空**——合并原 `versions/platform/0005_sys_tenant_db_key_nullable.py` 语义（06_01 起注册表
  不再写入该列，库键一律由 `tenant_{service}_{code}` 派生，见 `bms_core/db/keys.py`；物理删列另立任务）；
- 字段 / 索引口径与 ORM 模型（`bms_tenant/models/tenant.py::SysTenant`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 只建表不写种子（种子走 `ops/seed_tenant.py` 幂等脚本）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_sys_tenant"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("tenant:platform",)
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建租户注册表（含唯一约束与索引）。"""
    op.create_table(
        "sys_tenant",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column("code", sa.String(length=64), nullable=False, comment="租户编码（全小写）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="租户名称"),
        sa.Column("domain", sa.String(length=255), nullable=True, comment="子域名"),
        sa.Column(
            "db_key",
            sa.String(length=64),
            nullable=True,
            comment="已废弃（06_01 起不再写入；库键由 tenant_{service}_{code} 派生）",
        ),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态（active/suspended）"),
        sa.Column("expire_at", sa.DateTime(), nullable=True, comment="到期时间（UTC）"),
        sa.UniqueConstraint("code", "deleted_at", name="uq_sys_tenant_code_deleted_at"),
    )
    op.create_index("idx_sys_tenant_deleted_at", "sys_tenant", ["deleted_at"])
    op.create_index("idx_sys_tenant_domain", "sys_tenant", ["domain"])


def downgrade() -> None:
    """删除租户注册表。"""
    op.drop_table("sys_tenant")
