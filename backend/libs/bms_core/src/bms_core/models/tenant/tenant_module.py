"""租户-模块关系模型：`sys_tenant_module`（平台服务库 `bms_tenant`）。

- 语义：租户开通的模块清单与启停状态；一租户 × 一模块一行。
- 关联表口径：不落 `form_key` / `parent_id`；`module_key` 为跨库逻辑外键（→ `sys_module.code`）。
- 未勾选 = 无行 = 未开通；停用只切 `status`，不删行（存量数据保留可查）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_tenant_module`）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.base import BaseModel

TENANT_MODULE_ENABLED = "enabled"
"""模块状态：已开通。"""

TENANT_MODULE_DISABLED = "disabled"
"""模块状态：已停用。"""

TENANT_MODULE_STATUSES: ConcurrentStableList[str] = ConcurrentStableList(
    (TENANT_MODULE_ENABLED, TENANT_MODULE_DISABLED)
)
"""模块状态取值清单。"""


class SysTenantModule(BaseModel):
    """租户-模块关系（`sys_tenant_module`）：开通清单与启停状态。"""

    __tablename__ = "sys_tenant_module"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "module_key", "deleted_at", name="uq_sys_tenant_module_tenant_module_key_deleted_at"
        ),
    )

    tenant_id: Mapped[int] = mapped_column(BigInteger, comment="租户主键（同库逻辑外键 → sys_tenant.id，只持值）")
    module_key: Mapped[str] = mapped_column(String(32), comment="模块标识（跨库逻辑外键 → sys_module.code）")
    status: Mapped[str] = mapped_column(String(16), default=TENANT_MODULE_ENABLED, comment="状态（enabled/disabled）")
    opened_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="开通操作人（平台租户 sys_user.id；引导 / 系统开通为 NULL）"
    )
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近开通时间（UTC）")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近停用时间（UTC）")
