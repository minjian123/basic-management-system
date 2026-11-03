"""审计日志域模型：分片台账（`sys_audit_shard`）。

- 两张日志表（`sys_operation_log` / `sys_login_log`）为**逻辑表名**，物理按月分片、运行期建表，
  不进入 `Base.metadata` 与迁移链；结构声明见 `bms_platform/domains/log/schema.py`。
- 本表记录已建分片与归档状态，供查询路由、预创建任务与 14_01 归档清单读取。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_audit_shard.md`）。
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

__all__ = ["SHARD_STATUS_ACTIVE", "SHARD_STATUS_ARCHIVED", "SysAuditShard"]

SHARD_STATUS_ACTIVE = "active"
"""分片可用（可写 / 可查）。"""

SHARD_STATUS_ARCHIVED = "archived"
"""分片已归档（只读；14_01 回写）。"""


class SysAuditShard(BaseModel):
    """审计分片台账（每类日志每月一行）。"""

    __tablename__ = "sys_audit_shard"
    # 台账行不软删：唯一约束不带 `deleted_at`（否则 NULL 互不相等，约束失效）
    __table_args__ = (UniqueConstraint("log_type", "shard_month", name="uq_sys_audit_shard_type_month"),)

    log_type: Mapped[str] = mapped_column(String(16), comment="日志类型（operation / login）")
    shard_month: Mapped[str] = mapped_column(String(6), comment="分片月份（yyyyMM）")
    physical_table: Mapped[str] = mapped_column(String(64), comment="物理表名")
    status: Mapped[str] = mapped_column(String(16), default=SHARD_STATUS_ACTIVE, comment="状态（active / archived）")
