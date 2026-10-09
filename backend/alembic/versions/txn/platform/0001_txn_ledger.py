"""跨服务事务账本三表（`txn:platform` 链首建，05_07 强一致专项）。

Revision ID: 0001_txn_ledger
Revises:
Create Date: 2026-10-09

- 归属链：`txn:platform`（`txn` 服务的**平台侧独立基础设施库** `bms_txn`，与业务库物理分离）；
- **不建 `tenant` 链、不为每租户建账本库**：TM 是纯跨库协调基础设施，**与租户 / 业务无关**；
- 三表**不含租户列、不分库不分区**；分支目标库以 `global_txn_branch.db_key`（**不透明库键**）表达；
- 字段 / 索引口径与 ORM 模型（`bms_txn/models/ledger.py`）与《数据库设计》表文件逐项一致；
- 公共字段对齐 `BaseModel`（雪花 ID / 审计 / 软删除 / 乐观锁）；
- 四库兼容：不使用方言专用类型；只建表不写种子。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_txn_ledger"
down_revision: str | None = None
branch_labels: Sequence[str] | None = ("txn:platform",)
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
    """建跨服务事务账本三表（含唯一约束与索引）。"""
    op.create_table(
        "txn_global",
        *_base_columns(),
        sa.Column("global_txn_id", sa.String(length=64), nullable=False, comment="全局事务标识（XA gtrid）"),
        sa.Column("caller_service", sa.String(length=64), nullable=False, comment="发起方服务键"),
        sa.Column("state", sa.String(length=24), nullable=False, comment="状态机取值（TXN_*）"),
        sa.Column("deadline_at", sa.DateTime(), nullable=False, comment="提交决定截止时间（UTC）"),
        sa.Column("decided_at", sa.DateTime(), nullable=True, comment="提交决定点时间（UTC）"),
        sa.UniqueConstraint("global_txn_id", "deleted_at", name="uq_txn_global_txn_id_deleted_at"),
        sa.Index("idx_txn_global_state", "state", "deadline_at"),
        sa.Index("idx_txn_global_deleted_at", "deleted_at"),
    )
    op.create_table(
        "txn_global_branch",
        *_base_columns(),
        sa.Column("global_txn_id", sa.String(length=64), nullable=False, comment="所属全局事务标识"),
        sa.Column("branch_id", sa.String(length=64), nullable=False, comment="分支标识（XA bqual）"),
        sa.Column("service", sa.String(length=64), nullable=False, comment="参与方服务键"),
        sa.Column("db_key", sa.String(length=128), nullable=False, comment="不透明库键（TM 不解释）"),
        sa.Column("xid", sa.String(length=160), nullable=False, comment="XA 事务标识"),
        sa.Column("state", sa.String(length=24), nullable=False, comment="分支状态（BRANCH_*）"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0"), comment="驱动重试次数"),
        sa.Column("last_error", sa.String(length=512), nullable=True, comment="最近一次驱动失败原因"),
        sa.Column("request_hash", sa.String(length=64), nullable=True, comment="分支执行载荷摘要（幂等）"),
        sa.UniqueConstraint(
            "global_txn_id", "branch_id", "deleted_at", name="uq_txn_global_branch_txn_branch_deleted_at"
        ),
        sa.Index("idx_txn_global_branch_txn", "global_txn_id", "state"),
        sa.Index("idx_txn_global_branch_state", "state", "updated_at"),
        sa.Index("idx_txn_global_branch_deleted_at", "deleted_at"),
    )
    op.create_table(
        "txn_global_recovery",
        *_base_columns(),
        sa.Column("global_txn_id", sa.String(length=64), nullable=False, comment="被处置的全局事务标识"),
        sa.Column("branch_id", sa.String(length=64), nullable=True, comment="被处置分支（空 = 整事务级）"),
        sa.Column("detected_at", sa.DateTime(), nullable=False, comment="发现时刻（UTC）"),
        sa.Column("hung_seconds", sa.Integer(), nullable=True, comment="悬挂时长（秒）"),
        sa.Column("action", sa.String(length=24), nullable=False, comment="处置动作（drive_commit / drive_rollback）"),
        sa.Column("actor", sa.String(length=64), nullable=False, comment="处置方（recoverer / operator）"),
        sa.Column("handler", sa.String(length=64), nullable=True, comment="人工处置的操作人标识"),
        sa.Column("conclusion", sa.String(length=255), nullable=True, comment="处置结论"),
        sa.Index("idx_txn_global_recovery_txn", "global_txn_id", "id"),
        sa.Index("idx_txn_global_recovery_detected_at", "detected_at"),
        sa.Index("idx_txn_global_recovery_deleted_at", "deleted_at"),
    )


def downgrade() -> None:
    """逆序回退：删三表（含索引与唯一约束）。"""
    op.drop_table("txn_global_recovery")
    op.drop_table("txn_global_branch")
    op.drop_table("txn_global")
