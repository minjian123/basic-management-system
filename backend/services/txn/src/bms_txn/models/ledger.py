"""跨服务事务账本 ORM 模型：`global_txn` / `global_txn_branch` / `global_txn_recovery`。

- **库归属**：平台侧独立基础设施库 `bms_txn`（`datasource = PLATFORM`），与业务库物理分离。
- **去租户**：三表**不含租户列、不分库不分区**；分支目标库以**不透明库键**（`db_key`）表达，
  TM 不作业务解释（详设 05_07 §4 / §8 第 7 项）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`global_txn` 等 3 表）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = ["GlobalTxn", "GlobalTxnBranch", "GlobalTxnRecovery"]


class GlobalTxn(BaseModel):
    """全局事务主记录（`global_txn`）：状态机 + 提交决定点（`decided_at`）。"""

    __tablename__ = "txn_global"
    __table_args__ = (
        UniqueConstraint("global_txn_id", "deleted_at", name="uq_txn_global_txn_id_deleted_at"),
        Index("idx_txn_global_state", "state", "deadline_at"),
    )

    global_txn_id: Mapped[str] = mapped_column(String(64), comment="全局事务标识（同时作为 XA gtrid）")
    caller_service: Mapped[str] = mapped_column(String(64), comment="发起方服务键")
    state: Mapped[str] = mapped_column(String(24), default="active", comment="状态机取值（TXN_*）")
    deadline_at: Mapped[datetime] = mapped_column(DateTime, comment="提交决定截止时间（UTC）")
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="提交决定点时间（UTC；非空即已过决定点）"
    )


class GlobalTxnBranch(BaseModel):
    """参与方分支（`global_txn_branch`）：分支状态 + `xid` + 驱动重试痕迹。"""

    __tablename__ = "txn_global_branch"
    __table_args__ = (
        UniqueConstraint("global_txn_id", "branch_id", "deleted_at", name="uq_txn_global_branch_txn_branch_deleted_at"),
        Index("idx_txn_global_branch_txn", "global_txn_id", "state"),
        Index("idx_txn_global_branch_state", "state", "updated_at"),
    )

    global_txn_id: Mapped[str] = mapped_column(String(64), comment="所属全局事务标识")
    branch_id: Mapped[str] = mapped_column(String(64), comment="分支标识（XA bqual）")
    service: Mapped[str] = mapped_column(String(64), comment="参与方服务键")
    db_key: Mapped[str] = mapped_column(String(128), comment="不透明库键（TM 不解释）")
    xid: Mapped[str] = mapped_column(String(160), comment="XA 事务标识（由 TM 生成）")
    state: Mapped[str] = mapped_column(String(24), default="active", comment="分支状态（BRANCH_*）")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="TM 驱动重试次数")
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="最近一次驱动失败原因")
    request_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分支执行载荷摘要（分支级幂等）"
    )


class GlobalTxnRecovery(BaseModel):
    """恢复 / 对账台账（`global_txn_recovery`）：处置动作**只驱动协议**、禁止改业务数据。"""

    __tablename__ = "txn_global_recovery"
    __table_args__ = (
        Index("idx_txn_global_recovery_txn", "global_txn_id", "id"),
        Index("idx_txn_global_recovery_detected_at", "detected_at"),
    )

    global_txn_id: Mapped[str] = mapped_column(String(64), comment="被处置的全局事务标识")
    branch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="被处置分支（空 = 整事务级）")
    detected_at: Mapped[datetime] = mapped_column(DateTime, comment="发现时刻（UTC）")
    hung_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="悬挂时长（秒）")
    action: Mapped[str] = mapped_column(String(24), comment="处置动作（drive_commit / drive_rollback）")
    actor: Mapped[str] = mapped_column(String(64), comment="处置方（recoverer / operator）")
    handler: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="人工处置的操作人标识")
    conclusion: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="处置结论")
