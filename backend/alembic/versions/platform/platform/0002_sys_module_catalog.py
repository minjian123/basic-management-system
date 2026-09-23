"""服务目录升格（`platform:platform` 链 0002）：sys_module 增服务维度与契约版本字段，段位改可空并去唯一。

Revision ID: 0002_sys_module_catalog
Revises: 0001_sys_module
Create Date: 2026-09-22

- 归属链：`platform:platform`（`platform` 服务的平台服务库 `bms_platform`）；四库通用，SQLite 经
  `batch_alter_table` 兼容（重建表）；
- 新列口径与 ORM 模型（`bms_platform/models/catalog.py::SysModule`）逐项一致；
- `errcode_segment` 改可空并删除 `uq_sys_module_segment_deleted_at`；
- `service_key` / `errcode_segment` 不建 DB 唯一（达梦多 NULL 差异规避；唯一性交启动 / CI 校验）；
- 只改结构不写种子（种子走 `ops/seed_module.py` 幂等 upsert）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_sys_module_catalog"
down_revision: str | None = "0001_sys_module"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """升格服务目录：加服务维度 / 契约版本列，段位改可空并去唯一。"""
    with op.batch_alter_table("sys_module") as batch:
        batch.add_column(
            sa.Column("service_key", sa.String(length=32), nullable=True, comment="服务维度标识（微服务工程名）")
        )
        batch.add_column(
            sa.Column("business_code", sa.String(length=64), nullable=True, comment="业务权限码（sys_business.code）")
        )
        batch.add_column(
            sa.Column(
                "service_group",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'foundation'"),
                comment="归属分组（foundation/capability/product）",
            )
        )
        batch.add_column(
            sa.Column(
                "build_batch", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="建设批次（0~3）"
            )
        )
        batch.add_column(
            sa.Column(
                "service_version",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'0.1.0'"),
                comment="服务版本（semver）",
            )
        )
        batch.add_column(
            sa.Column(
                "contract_version",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'0.1.0'"),
                comment="契约版本（semver）",
            )
        )
        batch.add_column(
            sa.Column("product_key", sa.String(length=32), nullable=True, comment="产品标识（biz/cw；空=平台）")
        )
        batch.alter_column("errcode_segment", existing_type=sa.String(length=8), nullable=True)
        batch.drop_constraint("uq_sys_module_segment_deleted_at", type_="unique")


def downgrade() -> None:
    """回退：恢复段位非空与唯一约束，删除服务维度 / 契约版本列。"""
    with op.batch_alter_table("sys_module") as batch:
        batch.alter_column("errcode_segment", existing_type=sa.String(length=8), nullable=False)
        batch.create_unique_constraint("uq_sys_module_segment_deleted_at", ["errcode_segment", "deleted_at"])
        for column in (
            "service_key",
            "business_code",
            "service_group",
            "build_batch",
            "service_version",
            "contract_version",
            "product_key",
        ):
            batch.drop_column(column)
