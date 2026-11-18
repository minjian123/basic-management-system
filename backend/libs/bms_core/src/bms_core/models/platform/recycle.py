"""回收站模型：超期清理批次（`sys_recycle_log`）。

- 归属：platform 服务租户库，业务域 `recycle`（承载服务 `platform`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 软删除数据本体不另建表，仍复用各业务表 `deleted_at`；本表只记**清理批次**；
- 与归档执行记录同构：同一次作业共享 `batch_key`，逐表一行，`status` 三态
  （`running` / `success` / `failed`），`running` 超时由下次作业回收为 `failed`；
- 表结构以《数据库设计》表文件 `sys_recycle_log.md` 为唯一事实源。
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = [
    "RECYCLE_LOG_STATUSES",
    "RECYCLE_LOG_STATUS_FAILED",
    "RECYCLE_LOG_STATUS_RUNNING",
    "RECYCLE_LOG_STATUS_SUCCESS",
    "SysRecycleLog",
]

RECYCLE_LOG_STATUS_RUNNING = "running"
"""清理批次执行中。"""

RECYCLE_LOG_STATUS_SUCCESS = "success"
"""清理批次成功。"""

RECYCLE_LOG_STATUS_FAILED = "failed"
"""清理批次失败。"""

RECYCLE_LOG_STATUSES = (RECYCLE_LOG_STATUS_RUNNING, RECYCLE_LOG_STATUS_SUCCESS, RECYCLE_LOG_STATUS_FAILED)
"""清理批次状态值域。"""


class SysRecycleLog(BaseModel):
    """回收站清理批次（`sys_recycle_log`，platform 服务租户库）。"""

    __tablename__ = "sys_recycle_log"
    __table_args__ = (
        UniqueConstraint("batch_key", "table_name", "deleted_at", name="uq_sys_recycle_log_batch_table"),
        Index("idx_sys_recycle_log_table_started", "table_name", "started_at"),
        Index("idx_sys_recycle_log_status", "status"),
    )

    batch_key: Mapped[str] = mapped_column(
        String(64), comment="批次键（同一次清理作业共享，如 recycle:20261118043000:ab12cd34）"
    )
    table_name: Mapped[str] = mapped_column(String(64), comment="被清理的逻辑表名")
    status: Mapped[str] = mapped_column(
        String(16), default=RECYCLE_LOG_STATUS_RUNNING, comment="状态（running/success/failed）"
    )
    retention_days: Mapped[int] = mapped_column(Integer, comment="本次清理采用的保留天数")
    cutoff_at: Mapped[datetime] = mapped_column(DateTime, comment="清理截止时刻（UTC；deleted_at < cutoff_at 才删）")
    deleted_count: Mapped[int] = mapped_column(Integer, default=0, comment="本表本批物理删除条数")
    cost_time: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="耗时（毫秒）")
    started_at: Mapped[datetime] = mapped_column(DateTime, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败摘要（截断 512）")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="明细 JSON（批次上限 / 实际批次数 / 备注）")
