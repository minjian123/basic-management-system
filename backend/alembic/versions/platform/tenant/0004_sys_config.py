"""系统参数表（`sys_config`，`platform:tenant` 链，03_08）：通用键值表 + 平台默认种子键。

Revision ID: 0004_sys_config
Revises: 0003_sys_outbox_event_version
Create Date: 2026-09-27

- 归属链：`platform:tenant`（`platform` 服务 × 各租户的租户库 `bms_platform_{tenant}`）；
- 字段 / 索引口径与 ORM 模型（`bms_core/config/models.py`）逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型（`sa.Text` 跨方言一致）；
- 索引命名对齐 `Base.metadata` 约定（`idx_{表}_{列}`）；只建表不写种子（种子走 `ops/seed_config.py`）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_sys_config"
down_revision: str | None = "0003_sys_outbox_event_version"
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
    """建系统参数表（含唯一约束与公共软删除索引）。"""
    op.create_table(
        "sys_config",
        *_base_columns(),
        sa.Column("config_key", sa.String(length=128), nullable=False, comment="参数键（点分小写，唯一）"),
        # 不设 server_default：TEXT/BLOB/JSON 在 MySQL 不允许默认值（跨方言兼容）；空值由应用侧缺省承载
        sa.Column("value", sa.Text(), nullable=False, comment="参数值（文本承载）"),
        sa.Column("remark", sa.String(length=255), nullable=True, comment="备注（参数用途说明）"),
        sa.UniqueConstraint("config_key", "deleted_at", name="uq_sys_config_config_key_deleted_at"),
    )
    op.create_index("idx_sys_config_deleted_at", "sys_config", ["deleted_at"])


def downgrade() -> None:
    """删系统参数表。"""
    op.drop_index("idx_sys_config_deleted_at", table_name="sys_config")
    op.drop_table("sys_config")
