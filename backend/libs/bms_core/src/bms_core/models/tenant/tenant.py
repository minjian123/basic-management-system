"""租户注册模型：`sys_tenant`（平台服务库 `bms_tenant`；06_03 由共享基座库迁入本服务）。

- 数据所有权：**租户与配置服务**（写方唯一）；其他服务经租户注册只读契约取数。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant`）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel, SnowflakeId

TENANT_KIND_BUSINESS = "business"
"""租户类型：业务租户（缺省）。"""

TENANT_KIND_PLATFORM = "platform"
"""租户类型：平台租户（承载平台超管账号 / 角色 / 会话；全局唯一一条，`04_01`）。"""

TENANT_STATUS_PROVISIONING = "provisioning"
"""租户状态：开通中（注册行已落、建库/建表/种子未完成）。"""

TENANT_STATUS_ACTIVE = "active"
"""租户状态：启用。"""

TENANT_STATUS_SUSPENDED = "suspended"
"""租户状态：停用。"""

TENANT_STATUS_DELETED = "deleted"
"""租户状态：已注销（保留期内可恢复；**不软删**——`deleted_at` 保持 NULL 到物理清理，见任务 `04_03`）。"""


class SysTenant(BaseModel):
    """租户注册表（`sys_tenant`）：租户注册与路由依据（平台服务库）。

    `db_key` 为**废弃列**（06_01 起不再写入）：服务化后租户库键一律由
    `tenant_{service}_{code}` 派生，注册表不再持有数据源键；物理删列另立任务。
    """

    __tablename__ = "sys_tenant"
    __table_args__ = (
        UniqueConstraint("code", "deleted_at", name="uq_sys_tenant_code_deleted_at"),
        UniqueConstraint("form_key", "deleted_at", name="uq_sys_tenant_form_key_deleted_at"),
        UniqueConstraint("domain", "deleted_at", name="uq_sys_tenant_domain_deleted_at"),
        # 清理扫描与回填扫描共用：`status = deleted AND purge_at <= now` / `purge_at IS NULL`（任务 04_03）
        Index("idx_sys_tenant_purge_at", "status", "purge_at"),
    )

    form_key: Mapped[str] = mapped_column(
        String(64), default="tenant", comment="表单标识（多表联合判别列；全局唯一、保存后不变）"
    )
    kind: Mapped[str] = mapped_column(
        String(16), default=TENANT_KIND_BUSINESS, comment="租户类型（business 业务 / platform 平台租户）"
    )
    code: Mapped[str] = mapped_column(String(64), comment="租户编码（全小写）")
    name: Mapped[str] = mapped_column(String(128), comment="租户名称")
    domain: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="子域名（子域名租户路由依据；未删行唯一）"
    )
    db_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="已废弃（06_01 起不再写入；库键由 tenant_{service}_{code} 派生）",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default=TENANT_STATUS_ACTIVE,
        comment="状态（provisioning/active/suspended/deleted）",
    )
    expire_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="到期时间（UTC）")
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="注销申请时刻（UTC）；恢复时清空"
    )
    purge_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="保留期截止（UTC）；为空表示尚未进入清理倒计时（归档未就绪 / 待回填）",
    )
    parent_id: Mapped[int | None] = mapped_column(
        SnowflakeId, nullable=True, comment="上级字典 ID（自引用同表 id；顶层 NULL）"
    )
