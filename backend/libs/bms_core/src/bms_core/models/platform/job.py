"""作业中心平台侧模型：作业类型目录与监控投影（业务域 `job`，平台库）。

- 归属：`platform` 服务、库类别 `platform`（链 `platform:platform`），表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- `sys_job_type` 是 `[[jobs]]` 清单声明的**只读投影**（`content_hash` 去重，退役不删行）；
- `sys_job_monitor` 由平台 `job-monitor` 消费组按 `job_id` upsert（`last_event_at` 防旧事件覆盖）；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_job_type.md` / `sys_job_monitor.md`）。
"""

from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId

__all__ = [
    "JOB_TYPE_STATUSES",
    "JOB_TYPE_STATUS_DEPRECATED",
    "JOB_TYPE_STATUS_ENABLED",
    "JOB_TYPE_STATUS_RETIRED",
    "SysJobMonitor",
    "SysJobType",
]

JOB_TYPE_STATUS_ENABLED = "enabled"
"""作业类型启用：可提交、可执行。"""

JOB_TYPE_STATUS_DEPRECATED = "deprecated"
"""作业类型弃用：仍可执行历史作业，不再接受新提交。"""

JOB_TYPE_STATUS_RETIRED = "retired"
"""作业类型退役：仅保留目录行供历史作业解释。"""

JOB_TYPE_STATUSES = (JOB_TYPE_STATUS_ENABLED, JOB_TYPE_STATUS_DEPRECATED, JOB_TYPE_STATUS_RETIRED)
"""作业类型目录状态取值。"""


class SysJobType(BaseModel):
    """作业类型目录（`sys_job_type`）：声明投影，平台不手写产品记录。"""

    __tablename__ = "sys_job_type"
    __table_args__ = (
        UniqueConstraint("job_type", name="uq_sys_job_type"),
        Index("idx_sys_job_type_service", "service_key", "status"),
    )

    job_type: Mapped[str] = mapped_column(String(128), comment="作业类型（全局唯一）")
    service_key: Mapped[str] = mapped_column(String(64), comment="提供方服务键（执行者所在服务）")
    domain_key: Mapped[str] = mapped_column(String(64), comment="提供方业务域（域布局登记）")
    handler: Mapped[str] = mapped_column(String(256), comment="执行者点分路径（module:attr）")
    description: Mapped[str] = mapped_column(String(255), comment="说明（目录展示）")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=1800, comment="单次执行超时（提示 / 监控）")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, comment="最大执行次数")
    backoff_seconds: Mapped[int] = mapped_column(Integer, default=30, comment="退避基数（秒）")
    concurrency: Mapped[int] = mapped_column(Integer, default=4, comment="单租户该类型并发上限")
    payload_version: Mapped[str] = mapped_column(String(16), default="1.0.0", comment="负载版本")
    status: Mapped[str] = mapped_column(
        String(16), default=JOB_TYPE_STATUS_ENABLED, comment="状态（enabled/deprecated/retired）"
    )
    source: Mapped[str] = mapped_column(String(16), comment="声明来源（platform/product）")
    content_hash: Mapped[str] = mapped_column(CHAR(64), comment="声明要素稳定哈希（未变不写）")


class SysJobMonitor(BaseModel):
    """平台作业监控投影（`sys_job_monitor`）：四条生命周期事件 upsert，可重建。"""

    __tablename__ = "sys_job_monitor"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_sys_job_monitor_job_id"),
        Index("idx_sys_job_monitor_status", "status", "last_event_at"),
        Index("idx_sys_job_monitor_type", "job_type", "last_event_at"),
        Index("idx_sys_job_monitor_tenant", "tenant_id", "last_event_at"),
    )

    job_id: Mapped[int] = mapped_column(SnowflakeId, comment="作业标识（sys_job.id；跨服务全局唯一）")
    service_key: Mapped[str] = mapped_column(String(64), comment="提供方服务键（取消 / 重试转发依据）")
    job_type: Mapped[str] = mapped_column(String(128), comment="作业类型")
    tenant_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="租户主键（平台链作业为空）"
    )
    status: Mapped[str] = mapped_column(String(16), comment="作业状态（六态同 sys_job）")
    progress_done: Mapped[int] = mapped_column(BigInteger, default=0, comment="已完成量")
    progress_total: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="总量（NULL = 不确定进度）"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, comment="尝试次数")
    error: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="错误摘要（截断）")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="提交时刻（事件）")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时刻（事件）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="终态时刻（事件）")
    last_event_at: Mapped[datetime] = mapped_column(DateTime, comment="最近事件时刻（防旧事件覆盖）")
