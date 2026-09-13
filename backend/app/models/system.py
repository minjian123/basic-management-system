"""系统平台表模型骨架：任务定义与执行记录（调度入库在阶段六回补落地）。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SysTask(BaseModel):
    """任务定义（`sys_task`）：调度配置与执行体登记。"""

    __tablename__ = "sys_task"
    __table_args__ = (UniqueConstraint("name", "deleted_at", name="uq_sys_task_name_deleted_at"),)

    name: Mapped[str] = mapped_column(String(128), comment="任务名（唯一）")
    handler: Mapped[str] = mapped_column(String(256), comment="执行体（调用路径）")
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="调度表达式（NULL=手动触发）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")


class SysTaskLog(BaseModel):
    """任务执行记录（`sys_task_log`）。"""

    __tablename__ = "sys_task_log"

    task_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="任务定义 ID")
    status: Mapped[str] = mapped_column(String(16), comment="执行状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行结果 / 异常摘要")
