"""租户库名对照表（`tenant:platform` 链 0004，10_04）：新建 sys_tenant_database + 回填 db_basis。

Revision ID: 0004_sys_tenant_database
Revises: 0003_sys_outbox_event_version
Create Date: 2026-09-29

- 归属链：`tenant:platform`（`tenant` 服务的平台服务库 `bms_tenant`）；
- 语义：租户主键 ↔ 库名基对照（10_01 §3.2；一租户一行，各服务共享同一基）；
- 字段 / 索引口径与 ORM 模型（`bms_tenant/models/tenant_database.py::SysTenantDatabase`）逐项一致；
- 存量租户回填 `db_basis = 当前 code`（幂等：按未软删对照行判存）；时间取 Python 侧 UTC、
  雪花 id 取应用生成器（禁数据库端时间函数）；
- 列类型迁移（发件箱 / 死信）见同链 `0005_sys_outbox_tenant_bigint.py`。
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op
from bms_core.core.id import id_generator

revision: str = "0004_sys_tenant_database"
down_revision: str | None = "0003_sys_outbox_event_version"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """建租户库名对照表并回填存量租户。"""
    op.create_table(
        "sys_tenant_database",
        sa.Column("id", sa.BigInteger(), primary_key=True, comment="主键（雪花 ID）"),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("created_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.Column("updated_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True, comment="软删除时间（NULL=未删）"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1"), comment="乐观锁版本"),
        sa.Column(
            "tenant_id", sa.BigInteger(), nullable=False, comment="租户主键（同库逻辑外键 → sys_tenant.id，只持值）"
        ),
        sa.Column(
            "db_basis",
            sa.String(length=64),
            nullable=False,
            comment="库名基（创建时冻结的租户编码，稳定不可变）",
        ),
        sa.UniqueConstraint("tenant_id", "deleted_at", name="uq_sys_tenant_database_tenant_deleted_at"),
    )
    op.create_index("idx_sys_tenant_database_deleted_at", "sys_tenant_database", ["deleted_at"])
    _backfill_db_basis()


def _backfill_db_basis() -> None:
    """存量租户回填 `db_basis = 当前 code`（按未软删对照行判存，幂等）。"""
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, code FROM sys_tenant WHERE deleted_at IS NULL")).fetchall()
    now = datetime.now(UTC).replace(tzinfo=None)
    for tenant_id, code in rows:
        exists = connection.execute(
            sa.text("SELECT 1 FROM sys_tenant_database WHERE tenant_id = :tenant_id AND deleted_at IS NULL"),
            {"tenant_id": tenant_id},
        ).first()
        if exists:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO sys_tenant_database "
                "(id, created_at, created_by, updated_at, updated_by, deleted_at, version, tenant_id, db_basis) "
                "VALUES (:id, :now, NULL, :now, NULL, NULL, 1, :tenant_id, :db_basis)"
            ),
            {"id": id_generator.next_id(), "now": now, "tenant_id": tenant_id, "db_basis": code},
        )


def downgrade() -> None:
    """删除租户库名对照表。"""
    op.drop_table("sys_tenant_database")
