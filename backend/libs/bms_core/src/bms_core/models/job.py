"""异步作业模型：作业记录与行级错误明细（基础设施表，`owner=*`、双链）。

- 归属：每服务平台库 + 每服务租户库各一份（`deploy/boundaries/domain_layout.json` 不登记；
  由部署单元级建表集追加），表级归属见 `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 状态机：`queued` / `running` / `succeeded` / `failed` / `canceled` / `dead`（终态不可回退）；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_job.md` / `sys_job_error.md`）；
- 保留期：终态作业 30 天，由内置清理作业硬删；`queued` / `running` 永不删除。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId

__all__ = [
    "JOB_STATUS_CANCELED",
    "JOB_STATUS_DEAD",
    "JOB_STATUS_FAILED",
    "JOB_STATUS_QUEUED",
    "JOB_STATUS_RUNNING",
    "JOB_STATUS_SUCCEEDED",
    "JOB_TERMINAL_STATUSES",
    "SysJob",
    "SysJobError",
]

DEFAULT_PAYLOAD_VERSION = "1.0.0"
"""负载版本缺省值（与 `sys_job.payload_version` 一致）。"""

JOB_STATUS_QUEUED = "queued"
"""待执行（提交成功，等待抢占）。"""

JOB_STATUS_RUNNING = "running"
"""执行中（持有租约）。"""

JOB_STATUS_SUCCEEDED = "succeeded"
"""成功终态。"""

JOB_STATUS_FAILED = "failed"
"""失败终态（业务失败 / 不可重试）。"""

JOB_STATUS_CANCELED = "canceled"
"""取消终态。"""

JOB_STATUS_DEAD = "dead"
"""死信终态（重试耗尽 / 系统异常，可人工重试）。"""

JOB_TERMINAL_STATUSES = (
    JOB_STATUS_SUCCEEDED,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELED,
    JOB_STATUS_DEAD,
)
"""终态集合（不可回退）。"""


class SysJob(BaseModel):
    """异步作业记录（`sys_job`）：提交即持久，靠状态机 + 租约驱动执行。"""

    __tablename__ = "sys_job"
    __table_args__ = (
        UniqueConstraint("job_type", "idempotency_key", name="uq_sys_job_idempotency"),
        Index("idx_sys_job_claim", "status", "next_run_at", "priority", "id"),
        Index("idx_sys_job_lease", "status", "lease_until"),
        Index("idx_sys_job_type_created", "job_type", "created_at"),
        Index("idx_sys_job_creator", "created_by", "created_at"),
        Index("idx_sys_job_tenant_status", "tenant_id", "status"),
    )

    job_type: Mapped[str] = mapped_column(String(128), comment="作业类型（全局唯一，与 [[jobs]] 声明一致）")
    service_key: Mapped[str] = mapped_column(String(64), comment="提供方服务键（执行者所在服务）")
    domain_key: Mapped[str] = mapped_column(String(64), comment="提供方业务域（取自声明）")
    tenant_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="租户主键（雪花 id；平台链作业为空）"
    )
    status: Mapped[str] = mapped_column(String(16), default=JOB_STATUS_QUEUED, comment="状态（六态）")
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="租户内优先级（大者先；不跨租户抢占）")
    payload: Mapped[str] = mapped_column(Text, comment="负载 JSON（业务无关）")
    payload_version: Mapped[str] = mapped_column(
        String(16), default=DEFAULT_PAYLOAD_VERSION, comment="负载版本（语义化版本）"
    )
    result: Mapped[str | None] = mapped_column(Text, nullable=True, comment="结果 JSON 摘要（按上限截断）")
    progress_done: Mapped[int] = mapped_column(BigInteger, default=0, comment="已完成量")
    progress_total: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="总量（NULL = 不确定进度）"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="已执行次数（每次抢占 +1）")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, comment="最大执行次数（提交时快照）")
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="下次可执行时刻（退避 / 延迟；NULL = 立即可执行）"
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="当前执行者（worker 实例标识）")
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="租约到期时刻（失联回收依据）"
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近心跳时刻（排障 / 指标）"
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否请求取消")
    error: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败 / 死信摘要（截断）")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="备注（取消原因 / 运维说明）")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="提交幂等键（同类型内唯一）"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="首次开始时刻（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="终态时刻（UTC）")


class SysJobError(BaseModel):
    """作业行级错误明细（`sys_job_error`）：导入等万行错误完整存储，随作业硬删。"""

    __tablename__ = "sys_job_error"
    __table_args__ = (Index("idx_sys_job_error_job", "job_id", "id"),)

    job_id: Mapped[int] = mapped_column(SnowflakeId, comment="所属作业（sys_job.id；逻辑外键）")
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="业务行号（导入 Excel 行，自 2 起）")
    column_key: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="出错列 / 字段键")
    item_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="业务条目标识（非行号场景）")
    message: Mapped[str] = mapped_column(String(512), comment="错误原因（可读文案 / 文案键；截断 512）")
