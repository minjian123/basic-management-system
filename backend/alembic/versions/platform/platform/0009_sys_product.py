"""产品档案表（`platform:platform` 链 0009，12_01 产品注册机制 R4.1）。

Revision ID: 0009_sys_product
Revises: 0008_menu_form_multi
Create Date: 2026-10-07

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；
- 建 `sys_product`（`product_key` / `name` / `frontend_package_source` / `status` + 公共字段）；
- 唯一约束 `(product_key, deleted_at)`（软删除后可复用）；公共软删除索引 `idx_sys_product_deleted_at`
  （《数据规范》「公共软删除索引」口径）；
- 字段 / 索引口径与 ORM 模型（`bms_platform/models/catalog.py::SysProduct`）逐项一致；
- 只建表不写种子（产品档案三行走 `ops/seed_module.py` 幂等 upsert，`PRODUCT_CATALOG` 单一来源）；
- 四库通用：只 `create_table` + `create_index`（无方言专用类型，SQLite 无需重建表）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_sys_product"
down_revision: str | None = "0008_menu_form_multi"
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
    """建产品档案表 `sys_product`（含唯一约束与软删除索引）。"""
    op.create_table(
        "sys_product",
        *_base_columns(),
        sa.Column("product_key", sa.String(length=32), nullable=False, comment="产品标识（如 mdm / biz / cw）"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="产品名称（默认文案）"),
        sa.Column(
            "frontend_package_source",
            sa.String(length=255),
            nullable=True,
            comment="前端包来源（产品前端模块产物的获取来源；本期留空）",
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'enabled'"),
            comment="状态（enabled/disabled/planned/retired）",
        ),
        sa.UniqueConstraint("product_key", "deleted_at", name="uq_sys_product_key_deleted_at"),
    )
    op.create_index("idx_sys_product_deleted_at", "sys_product", ["deleted_at"])


def downgrade() -> None:
    """删产品档案表（含软删除索引）。"""
    op.drop_index("idx_sys_product_deleted_at", table_name="sys_product")
    op.drop_table("sys_product")
