"""任务调度模型：任务定义与执行记录（`task` 业务域）。

- 归属：业务域 `task`（承载服务 `platform`，库类别 `tenant`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_task.md` / `sys_task_log.md`）；
- 状态口径：`sys_task` 的 `enabled` 与 `status` 双列**同步写入**（`enabled = status == "enabled"`），
  读取一律以 `status` 为准，不设第二套真值。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

TASK_STATUS_ENABLED = "enabled"
"""任务启用状态（`sys_task.status`）：参与调度。"""

TASK_STATUS_DISABLED = "disabled"
"""任务停用状态（`sys_task.status`）：保留定义与历史，不再派发。"""

TASK_RUN_RUNNING = "running"
"""执行记录状态：已派发、执行中（超时未完成由调度器回收为 `failed`）。"""

TASK_RUN_SUCCESS = "success"
"""执行记录状态：执行成功。"""

TASK_RUN_FAILED = "failed"
"""执行记录状态：重试耗尽 / 超时未完成 / handler 不可解析。"""

TASK_RUN_SKIPPED = "skipped"
"""执行记录状态：已调度但执行体判定跳过（内置任务占位实现即此态）。"""

TASK_TRIGGER_SCHEDULE = "schedule"
"""触发来源：定时调度派发。"""

TASK_TRIGGER_MANUAL = "manual"
"""触发来源：页面手动触发。"""


class SysTask(BaseModel):
    """任务定义（`sys_task`）：调度配置与执行体登记。"""

    __tablename__ = "sys_task"
    __table_args__ = (
        UniqueConstraint("name", "deleted_at", name="uq_sys_task_name_deleted_at"),
        UniqueConstraint("code", "deleted_at", name="uq_sys_task_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_task_form_key_deleted_at"),
        Index("idx_sys_task_status_next_run_at", "status", "next_run_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="task", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="任务代码（如 cleanup_outbox）")
    name: Mapped[str] = mapped_column(String(128), comment="任务名（唯一）")
    handler: Mapped[str] = mapped_column(String(256), comment="执行体（调用路径）")
    cron: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="调度表达式（NULL=仅手动触发）")
    args: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务参数（JSON 对象或数组）")
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="下次到期时间（UTC；NULL=尚未计算 / 仅手动触发）"
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近一次派发时间（UTC）")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用（与 status 同步写入）")
    status: Mapped[str] = mapped_column(String(16), default=TASK_STATUS_ENABLED, comment="状态（enabled/disabled）")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="备注")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )


class SysTaskLog(BaseModel):
    """任务执行记录（`sys_task_log`）。"""

    __tablename__ = "sys_task_log"
    __table_args__ = (
        Index("idx_sys_task_log_task_id_started_at", "task_id", "started_at"),
        Index("idx_sys_task_log_status", "status"),
    )

    task_id: Mapped[int] = mapped_column(BigInteger, comment="任务定义 ID")
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="本次执行标识（UUID）")
    trigger_source: Mapped[str] = mapped_column(
        String(16), default=TASK_TRIGGER_SCHEDULE, comment="触发来源（schedule/manual）"
    )
    status: Mapped[str] = mapped_column(String(16), comment="执行状态（running/success/failed/skipped）")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="已重试次数")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    cost_time: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="耗时（毫秒）")
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="成功输出摘要")
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="错误摘要（截断 512）")
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="上级明细 ID（自引用同表 id；顶层 NULL）"
    )
