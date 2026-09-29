"""发件箱三表（`identity:tenant` 链，10_04 缺口补齐）。

Revision ID: 0004_sys_outbox
Revises: 0003_sys_client
Create Date: 2026-09-29

- 归属链：`identity:tenant`（`identity` 服务的租户库 `bms_identity_{db_basis}`）；
- **缺口补齐**：本链此前迁移未建基础设施表（发件箱三表），而表归属登记（`OWNER_EVERY_SERVICE` +
  `BOTH`）与链元数据要求每服务每条链各含三表；本迁移补齐，使该链零漂移；
- 结构按现模型（`bms_core/models/outbox.py`）：`tenant_id` 直接为 `BIGINT`（雪花租户主键）；
- 三表为基础设施账本：唯一约束**不并入 `deleted_at`**（发件箱 / 幂等要求跨方言严格唯一）；
- 与 `identity:platform` 链 `0002_sys_outbox.py` 同构，仅 revision / 链不同。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_sys_outbox"
down_revision: str | None = "0003_sys_client"
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
    """建事务性发件箱三表（含唯一约束与索引）。"""
    op.create_table(
        "sys_outbox",
        *_base_columns(),
        sa.Column("event_id", sa.String(length=64), nullable=False, comment="事件 ID（幂等键）"),
        sa.Column("event_type", sa.String(length=128), nullable=False, comment="事件类型（域.对象.动作）"),
        sa.Column(
            "event_version",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'1.0.0'"),
            comment="事件契约版本（X.Y.Z）",
        ),
        sa.Column("aggregate_key", sa.String(length=128), nullable=True, comment="聚合 / 分区键（同聚合按序）"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True, comment="租户主键（雪花 id）"),
        sa.Column("payload", sa.JSON(), nullable=False, comment="事件负载"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, comment="事件发生时间（UTC）"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", comment="投递状态"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="已重试次数"),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True, comment="下次可投递时间"),
        sa.Column("delivered_at", sa.DateTime(), nullable=True, comment="投递成功时间（UTC）"),
        sa.Column("error_msg", sa.String(length=512), nullable=True, comment="最近一次失败原因"),
        sa.UniqueConstraint("event_id", name="uq_sys_outbox_event_id"),
    )
    op.create_index("idx_sys_outbox_deleted_at", "sys_outbox", ["deleted_at"])
    op.create_index("idx_sys_outbox_dispatch", "sys_outbox", ["status", "next_retry_at", "id"])
    op.create_index("idx_sys_outbox_aggregate", "sys_outbox", ["aggregate_key", "id"])

    op.create_table(
        "sys_event_consumed",
        *_base_columns(),
        sa.Column("consumer", sa.String(length=128), nullable=False, comment="消费者标识"),
        sa.Column("event_id", sa.String(length=64), nullable=False, comment="事件 ID"),
        sa.Column("event_type", sa.String(length=128), nullable=True, comment="事件类型（排障用）"),
        sa.UniqueConstraint("consumer", "event_id", name="uq_sys_event_consumed"),
    )
    op.create_index("idx_sys_event_consumed_deleted_at", "sys_event_consumed", ["deleted_at"])

    op.create_table(
        "sys_event_dead_letter",
        *_base_columns(),
        sa.Column("source", sa.String(length=16), nullable=False, comment="来源（outbox / consumer）"),
        sa.Column("event_id", sa.String(length=64), nullable=False, comment="事件 ID"),
        sa.Column("event_type", sa.String(length=128), nullable=False, comment="事件类型"),
        sa.Column("consumer", sa.String(length=128), nullable=True, comment="消费者标识（source=consumer）"),
        sa.Column("aggregate_key", sa.String(length=128), nullable=True, comment="聚合 / 分区键"),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True, comment="租户主键（雪花 id）"),
        sa.Column("payload", sa.JSON(), nullable=False, comment="事件负载"),
        sa.Column("error_msg", sa.String(length=512), nullable=False, comment="失败原因（截断）"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="已重试次数"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending", comment="处置状态"),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, comment="事件发生时间（UTC）"),
    )
    op.create_index("idx_sys_event_dead_letter_deleted_at", "sys_event_dead_letter", ["deleted_at"])
    op.create_index("idx_sys_event_dead_letter_status", "sys_event_dead_letter", ["status", "id"])


def downgrade() -> None:
    """逆序删除事务性发件箱三表。"""
    op.drop_table("sys_event_dead_letter")
    op.drop_table("sys_event_consumed")
    op.drop_table("sys_outbox")
