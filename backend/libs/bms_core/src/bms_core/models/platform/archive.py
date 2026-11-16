"""归档管理模型：策略、执行记录、归档行与归档链尾（业务域 `archive`）。

- 归属：业务域 `archive`（承载服务 `platform`）；表级归属见
  `bms_core/services/table_registry.py::TABLE_OWNERSHIP`；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_archive_policy.md` / `sys_archive_log.md` /
  `sys_archive_record.md` / `sys_archive_chain_tail.md`）；
- `sys_archive_record` 建在**归档库** `bms_archive`（`datasource=archive`），只追加、不继承 `BaseModel`
  （无软删除 / 无乐观锁）；其余三表在平台库，继承 `BaseModel`。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import Base, BaseModel, SnowflakeId, id_generator

__all__ = [
    "ARCHIVE_DISPOSE_CLEANUP",
    "ARCHIVE_DISPOSE_DESTROY",
    "ARCHIVE_LOG_STATUSES",
    "ARCHIVE_LOG_STATUS_FAILED",
    "ARCHIVE_LOG_STATUS_RUNNING",
    "ARCHIVE_LOG_STATUS_SKIPPED",
    "ARCHIVE_LOG_STATUS_SUCCESS",
    "ARCHIVE_POLICY_STATUS_DISABLED",
    "ARCHIVE_POLICY_STATUS_ENABLED",
    "ARCHIVE_TARGETS",
    "ARCHIVE_TARGET_ARCHIVE_DB",
    "ARCHIVE_TARGET_CLEANUP",
    "ARCHIVE_TARGET_DESTROY",
    "ARCHIVE_TARGET_MINIO",
    "SysArchiveChainTail",
    "SysArchiveLog",
    "SysArchivePolicy",
    "SysArchiveRecord",
]

ARCHIVE_TARGET_ARCHIVE_DB = "archive_db"
"""归档目标：两段式（热表 → 归档库 → 对象存储）。"""

ARCHIVE_TARGET_MINIO = "minio"
"""归档目标：直冷（热表 → 对象存储，跳过归档库）。"""

ARCHIVE_TARGET_CLEANUP = "cleanup"
"""执行记录目标：过期冷化文件清理。"""

ARCHIVE_TARGET_DESTROY = "destroy"
"""执行记录目标：合规销毁。"""

ARCHIVE_TARGETS = (ARCHIVE_TARGET_ARCHIVE_DB, ARCHIVE_TARGET_MINIO)
"""策略可选目标（清理 / 销毁是记录动作，不可配为策略目标）。"""

ARCHIVE_POLICY_STATUS_ENABLED = "enabled"
"""策略启用。"""

ARCHIVE_POLICY_STATUS_DISABLED = "disabled"
"""策略停用。"""

ARCHIVE_LOG_STATUS_RUNNING = "running"
"""执行记录：执行中。"""

ARCHIVE_LOG_STATUS_SUCCESS = "success"
"""执行记录：成功。"""

ARCHIVE_LOG_STATUS_FAILED = "failed"
"""执行记录：失败。"""

ARCHIVE_LOG_STATUS_SKIPPED = "skipped"
"""执行记录：跳过（并发未取得锁 / 无到期数据）。"""

ARCHIVE_LOG_STATUSES = (
    ARCHIVE_LOG_STATUS_RUNNING,
    ARCHIVE_LOG_STATUS_SUCCESS,
    ARCHIVE_LOG_STATUS_FAILED,
    ARCHIVE_LOG_STATUS_SKIPPED,
)
"""执行记录状态清单。"""

ARCHIVE_DISPOSE_CLEANUP = "cleanup"
"""冷化文件处置：到期清理。"""

ARCHIVE_DISPOSE_DESTROY = "destroy"
"""冷化文件处置：合规销毁。"""


class SysArchivePolicy(BaseModel):
    """归档策略（`sys_archive_policy`，平台库）。"""

    __tablename__ = "sys_archive_policy"
    __table_args__ = (
        UniqueConstraint("table_name", "deleted_at", name="uq_sys_archive_policy_table"),
        Index("idx_sys_archive_policy_status", "status"),
    )

    table_name: Mapped[str] = mapped_column(String(64), comment="逻辑表名（平台库已登记表）")
    time_field: Mapped[str] = mapped_column(String(64), comment="归档判定时间字段")
    threshold_days: Mapped[int] = mapped_column(Integer, default=90, comment="阈值天数")
    retention_days: Mapped[int] = mapped_column(Integer, default=180, comment="归档库保留天数")
    target: Mapped[str] = mapped_column(
        String(16), default=ARCHIVE_TARGET_ARCHIVE_DB, comment="归档目标（archive_db / minio）"
    )
    batch_size: Mapped[int] = mapped_column(Integer, default=1000, comment="单批迁移条数")
    status: Mapped[str] = mapped_column(
        String(16), default=ARCHIVE_POLICY_STATUS_ENABLED, comment="状态（enabled / disabled）"
    )
    require_chain: Mapped[bool] = mapped_column(Boolean, default=False, comment="归档前强制哈希链校验")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True, comment="备注")


class SysArchiveLog(BaseModel):
    """归档执行记录（`sys_archive_log`，平台库）。"""

    __tablename__ = "sys_archive_log"
    __table_args__ = (
        UniqueConstraint("batch_key", "deleted_at", name="uq_sys_archive_log_batch_key"),
        Index("idx_sys_archive_log_policy_started", "policy_id", "started_at"),
        Index("idx_sys_archive_log_status", "status"),
        Index("idx_sys_archive_log_dispose", "target", "retention_until", "disposed_at"),
    )

    policy_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="策略 ID")
    table_name: Mapped[str] = mapped_column(String(64), comment="源逻辑表名")
    batch_key: Mapped[str] = mapped_column(String(160), comment="批次幂等键")
    target: Mapped[str] = mapped_column(String(16), comment="动作 / 目标（archive_db / minio / cleanup / destroy）")
    tenant_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="租户主键（平台级批次为空）")
    archived_count: Mapped[int] = mapped_column(Integer, default=0, comment="本次处理条数")
    file_key: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="冷化数据对象 key")
    status: Mapped[str] = mapped_column(String(16), default=ARCHIVE_LOG_STATUS_RUNNING, comment="状态")
    cost_time: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="耗时（毫秒）")
    started_at: Mapped[datetime] = mapped_column(DateTime, comment="开始时间（UTC）")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（UTC）")
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="失败摘要")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="明细 JSON")
    retention_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="冷化文件保留到期时刻（UTC）"
    )
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="文件处置时刻（UTC）")
    dispose_type: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="处置类型（cleanup / destroy）")
    operator_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="手动触发 / 销毁操作人")


class SysArchiveRecord(Base):
    """归档数据行（`sys_archive_record`，归档库 `bms_archive`；只追加）。"""

    __tablename__ = "sys_archive_record"
    __table_args__ = (
        UniqueConstraint("source_table", "source_id", name="uq_sys_archive_record_source"),
        Index("idx_sys_archive_record_tenant", "tenant_id", "source_table", "archived_at"),
        Index("idx_sys_archive_record_policy", "policy_id", "archived_at"),
        Index("idx_sys_archive_record_time", "source_table", "archived_at"),
    )

    id: Mapped[int] = mapped_column(
        SnowflakeId,
        primary_key=True,
        autoincrement=False,
        default=id_generator.next_id,
        comment="主键（雪花 ID）",
    )
    tenant_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="租户主键（全局链为空）")
    source_table: Mapped[str] = mapped_column(String(64), comment="源逻辑表名")
    source_id: Mapped[str] = mapped_column(String(64), comment="源行主键（十进制字符串）")
    source_month: Mapped[str | None] = mapped_column(String(6), nullable=True, comment="源分片月份（yyyyMM）")
    source_datasource: Mapped[str] = mapped_column(String(16), default="platform", comment="源库类别")
    policy_id: Mapped[int] = mapped_column(SnowflakeId, comment="归档策略 ID")
    batch_id: Mapped[int] = mapped_column(SnowflakeId, comment="归档批次 ID")
    payload: Mapped[str] = mapped_column(Text, comment="源行完整字段 JSON")
    archived_at: Mapped[datetime] = mapped_column(DateTime, comment="归档时刻（UTC）")


class SysArchiveChainTail(BaseModel):
    """归档链尾（`sys_archive_chain_tail`，平台库；审计分片删表后的校验依据）。"""

    __tablename__ = "sys_archive_chain_tail"
    __table_args__ = (
        UniqueConstraint("log_type", "shard_month", "tenant_key", name="uq_sys_archive_chain_tail_month"),
        Index("idx_sys_archive_chain_tail_lookup", "log_type", "shard_month"),
    )

    log_type: Mapped[str] = mapped_column(String(16), comment="日志类型（operation / login / data_audit）")
    shard_month: Mapped[str] = mapped_column(String(6), comment="分片月份（yyyyMM）")
    tenant_key: Mapped[str] = mapped_column(String(32), comment="链所属租户键（global 或雪花 id 字符串）")
    first_prev_hash: Mapped[str] = mapped_column(String(64), comment="该月该租户首条 prev_hash")
    last_record_hash: Mapped[str] = mapped_column(String(64), comment="该月该租户末条 record_hash")
    record_count: Mapped[int] = mapped_column(Integer, default=0, comment="该月该租户记录条数")
    archive_log_id: Mapped[int | None] = mapped_column(SnowflakeId, nullable=True, comment="对应归档批次 ID")
