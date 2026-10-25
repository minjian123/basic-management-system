"""任务调度模型：任务定义与执行记录（`task` 业务域）。

- 归属：业务域 `task`（承载服务 `platform`，库类别 `platform`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_task.md` / `sys_task_log.md`）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysTask(BaseModel):
    """任务定义（`sys_task`）：调度配置与执行体登记。"""

    __tablename__ = "sys_task"
    __table_args__ = (
        UniqueConstraint("name", "deleted_at", name="uq_sys_task_name_deleted_at"),
        UniqueConstraint("code", "deleted_at", name="uq_sys_task_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_task_form_key_deleted_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="task", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="任务代码（如 cleanup_outbox）")
    name: Mapped[str] = mapped_column(String(128), comment="任务名（唯一）")
    handler: Mapped[str] = mapped_column(String(256), comment="执行体（调用路径）")
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="调度表达式（NULL=手动触发）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysTaskLog(BaseModel):
    """任务执行记录（`sys_task_log`）。"""

    __tablename__ = "sys_task_log"

    task_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="任务定义 ID")
    status: Mapped[str] = mapped_column(String(16), comment="执行状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行结果 / 异常摘要")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )
