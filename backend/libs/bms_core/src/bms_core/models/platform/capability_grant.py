"""跨产品能力分配授权模型（`sys_capability_grant`，07B `02_04`）：平台服务自有。

- **一行 = 一个「能力 × 消费方」的授权记录**：粒度能力级；数据范围仍由既有数据权限体系约束；
- **来源两层**：`declared`（随产品自持声明的 `default_consumers` 装载）/ `manual`（平台管理面人工授予）；
- **撤销不删行**：只切 `status` 与 `revoked_at`，保留授权历史；软删除仅用于误录清理；
- **不按租户**：授权是平台级全局数据（服务实例跨租户共享），故无 `tenant_id` 列；
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_capability_grant.md`），字段级口径不在本文件重复。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

GRANT_SOURCE_DECLARED = "declared"
"""来源：产品自持声明装载（`collaborations[].default_consumers`）。"""

GRANT_SOURCE_MANUAL = "manual"
"""来源：平台管理面人工授予。"""

GRANT_STATUS_ENABLED = "enabled"
"""状态：有效（参与入站校验与出站 scope 派生）。"""

GRANT_STATUS_DISABLED = "disabled"
"""状态：已撤销（保留历史；声明装载不重新打开人工撤销的记录）。"""

GRANT_NOTE_DECLARED = "产品声明默认消费方"
"""声明装载写入的缺省说明。"""

GRANT_NOTE_REMOVED = "声明移除"
"""声明移除时写入的说明（同值记录在声明回归时恢复有效）。"""


class SysCapabilityGrant(BaseModel):
    """能力分配授权表（`sys_capability_grant`）：能力 × 消费方的授权记录。

    唯一键 `(capability_name, consumer_key, deleted_at)` —— 一能力一消费方一条记录；
    撤销后重新授予走同一行，软删除后才可重录（规避达梦多 NULL 差异的同口径写法）。
    """

    __tablename__ = "sys_capability_grant"
    __table_args__ = (
        UniqueConstraint(
            "capability_name",
            "consumer_key",
            "deleted_at",
            name="uq_sys_capability_grant_capability_consumer_deleted_at",
        ),
        Index("idx_sys_capability_grant_consumer_status", "consumer_key", "status"),
        Index("idx_sys_capability_grant_capability_status", "capability_name", "status"),
    )

    capability_name: Mapped[str] = mapped_column(
        String(128), comment="能力名（跨源逻辑外键 → 产品自持声明的 collaborations[].name，只持值）"
    )
    consumer_key: Mapped[str] = mapped_column(
        String(64), comment="消费方标识（服务键或产品键；写入前经服务目录 / 产品档案校验已登记）"
    )
    source: Mapped[str] = mapped_column(
        String(16), default=GRANT_SOURCE_DECLARED, comment="来源（declared 声明装载 / manual 人工授予）"
    )
    status: Mapped[str] = mapped_column(
        String(16), default=GRANT_STATUS_ENABLED, comment="状态（enabled 有效 / disabled 已撤销）"
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="有效期截止（UTC；NULL=长期有效；过期视为无效，运行时判定）"
    )
    granted_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="授予人（sys_user.id；声明装载为 NULL）"
    )
    granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="授予时间（UTC）")
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最近撤销时间（UTC；重新授予时清空）"
    )
    note: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="说明 / 授予理由（声明装载写默认说明；临时授权必填）"
    )
