"""用户扩展信息表（`sys_user_extension`，`platform:tenant` 链，域 06 具名插槽）。

Revision ID: 0006_sys_user_extension
Revises: 0005_sys_outbox_tenant_bigint
Create Date: 2026-10-03

- 归属链：`platform:tenant`（`platform` 服务 × 各租户的租户库 `bms_platform_{db_basis}`）；
- 字段 / 索引口径与 ORM 模型（`bms_platform/models/system.py::SysUserExtension`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型；
- 索引命名对齐 `Base.metadata` 约定（`idx_{表}_{列}` / `uq_{表}_{列}`）；只建表不写种子。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_sys_user_extension"
down_revision: str | None = "0005_sys_outbox_tenant_bigint"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """公共字段（对齐 `BaseModel`）。

    Returns:
        list[sa.Column]: 公共列定义。
    """
    return [
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
    ]


def upgrade() -> None:
    """建用户扩展信息表（含同用户同标签唯一约束与索引）。"""
    op.create_table(
        "sys_user_extension",
        *_base_columns(),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="用户主键（逻辑外键 → sys_user.id）"),
        sa.Column("label", sa.String(length=64), nullable=False, comment="扩展标签（用户维度内唯一）"),
        sa.Column("remark", sa.String(length=255), nullable=True, comment="备注"),
        sa.UniqueConstraint("user_id", "label", "deleted_at", name="uq_sys_user_extension_user_label_deleted_at"),
    )
    op.create_index("idx_sys_user_extension_user_id", "sys_user_extension", ["user_id"])
    op.create_index("idx_sys_user_extension_deleted_at", "sys_user_extension", ["deleted_at"])


def downgrade() -> None:
    """删用户扩展信息表。"""
    op.drop_index("idx_sys_user_extension_deleted_at", table_name="sys_user_extension")
    op.drop_index("idx_sys_user_extension_user_id", table_name="sys_user_extension")
    op.drop_table("sys_user_extension")
