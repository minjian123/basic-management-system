"""账号锁定记录模型：`sys_account_lock`（组织主数据服务租户库 `bms_org_{code}`）。

- 数据所有权：**组织主数据服务**（与 `sys_user` 同库；锁定记录与账号状态一致）。
- `lock_type` 三型：`fail_limit`（登录失败触发，认证链路写入）/ `inactive`（长期未登录扫描写入）/
  `manual`（管理员手动锁定）；本模块（阶段六 03_07）负责任务扩展与手动解锁，`inactive` 由 03_05 写入。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_account_lock`）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel

LOCK_TYPE_FAIL_LIMIT = "fail_limit"
"""锁定类型：登录失败达阈值触发。"""

LOCK_TYPE_INACTIVE = "inactive"
"""锁定类型：长期未登录自动锁定（定时 / 手动扫描触发）。"""

LOCK_TYPE_MANUAL = "manual"
"""锁定类型：管理员手动锁定。"""

LOCK_TYPES: tuple[str, ...] = (LOCK_TYPE_FAIL_LIMIT, LOCK_TYPE_INACTIVE, LOCK_TYPE_MANUAL)
"""锁定类型取值清单。"""


class SysAccountLock(BaseModel):
    """账号锁定记录（`sys_account_lock`）：锁定类型 / 原因 / 时间 / 操作人与解锁信息。"""

    __tablename__ = "sys_account_lock"
    __table_args__ = (
        Index("idx_sys_account_lock_user_locked", "user_id", "locked_at"),
        Index("idx_sys_account_lock_user_unlock", "user_id", "unlock_at"),
        Index("idx_sys_account_lock_unlock_by", "unlock_by"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, comment="用户主键（逻辑外键 sys_user.id）")
    lock_type: Mapped[str] = mapped_column(String(16), comment="锁定类型（fail_limit/inactive/manual）")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="锁定原因")
    locked_at: Mapped[datetime] = mapped_column(DateTime, comment="锁定时间（UTC）")
    locked_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="锁定操作人（inactive / 系统触发为 NULL）"
    )
    unlock_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="解锁时间（UTC；NULL=未解锁）")
    unlock_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="解锁操作人（NULL=未解锁）")
