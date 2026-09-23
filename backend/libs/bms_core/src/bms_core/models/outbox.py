"""事件一致性 ORM 模型：事务性发件箱与消费幂等 / 死信账本（平台库 + 租户库双链）。

- 三表均为基础设施账本：行不作软删除，唯一约束**不并入 `deleted_at`**（发件箱与幂等
  要求跨方言严格唯一，MySQL / PostgreSQL / SQLite 对复合唯一中的 NULL 视作互异，
  并入将失效），偏离说明见各表文件「物理账本口径」；公共字段仍随 `BaseModel` 保留。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_outbox` / `sys_event_consumed` /
  `sys_event_dead_letter`）；字段与索引口径与对应 Alembic 迁移逐项一致。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.events.base import DEFAULT_EVENT_VERSION
from bms_core.models.base import BaseModel

__all__ = ["SysEventConsumed", "SysEventDeadLetter", "SysOutbox"]


class SysOutbox(BaseModel):
    """事务性发件箱（`sys_outbox`）：业务事务内同库同事务写事件，投递器轮询转发并标记。"""

    __tablename__ = "sys_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_sys_outbox_event_id"),
        Index("idx_sys_outbox_dispatch", "status", "next_retry_at", "id"),
        Index("idx_sys_outbox_aggregate", "aggregate_key", "id"),
    )

    event_id: Mapped[str] = mapped_column(String(64), comment="事件 ID（幂等键）")
    event_type: Mapped[str] = mapped_column(String(128), comment="事件类型（域.对象.动作）")
    event_version: Mapped[str] = mapped_column(
        String(16), default=DEFAULT_EVENT_VERSION, comment="事件契约版本（X.Y.Z）"
    )
    aggregate_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="聚合 / 分区键（同聚合按序投递；空 = 独立事件）"
    )
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="租户标识")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, comment="事件负载")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, comment="事件发生时间（UTC）")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="投递状态（pending/delivered/dead）")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="已重试次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="下次可投递时间")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="投递成功时间（UTC）")
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="最近一次失败原因")


class SysEventConsumed(BaseModel):
    """消费幂等账本（`sys_event_consumed`）：`(consumer, event_id)` 唯一，命中即跳过。"""

    __tablename__ = "sys_event_consumed"
    __table_args__ = (UniqueConstraint("consumer", "event_id", name="uq_sys_event_consumed"),)

    consumer: Mapped[str] = mapped_column(String(128), comment="消费者标识（消费组 / 处理者）")
    event_id: Mapped[str] = mapped_column(String(64), comment="事件 ID（与 sys_outbox.event_id 同源）")
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="事件类型（排障用）")


class SysEventDeadLetter(BaseModel):
    """事件死信看板（`sys_event_dead_letter`）：投递 / 消费失败事件落库待人工处置。"""

    __tablename__ = "sys_event_dead_letter"
    __table_args__ = (Index("idx_sys_event_dead_letter_status", "status", "id"),)

    source: Mapped[str] = mapped_column(String(16), comment="来源（outbox / consumer）")
    event_id: Mapped[str] = mapped_column(String(64), comment="事件 ID（与 sys_outbox.event_id 同源）")
    event_type: Mapped[str] = mapped_column(String(128), comment="事件类型")
    consumer: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="消费者标识（source=consumer）")
    aggregate_key: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="聚合 / 分区键")
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="租户标识")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, comment="事件负载（便于重投 / 排障）")
    error_msg: Mapped[str] = mapped_column(String(512), comment="失败原因（截断）")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="转入死信前的已重试次数")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="处置状态（pending/replayed/ignored）")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, comment="事件发生时间（UTC）")
