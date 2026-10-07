"""用户与账号锁定模型：`sys_user` / `sys_account_lock`（platform 服务租户库 `bms_platform_{code}`）。

- 数据所有权：**平台服务**（用户＝系统账号，属权限 / 身份体系；02_05 由 org 服务租户库迁入，
  与角色 / 授权、字典 / 系统参数同库）。
- 本模型承载**本地登录所需字段**（账号 / 密码哈希 / 状态 / 锁定字段 / 密码策略字段 / 语言时区偏好）；
  完整用户档案与组织关系随用户管理阶段扩展（组织主数据归 mdm，用户归属部门 `dept_id` 引用组织主数据）。
- `sys_account_lock` 与 `sys_user` 同库；`lock_type` 三型：`fail_limit`（登录失败触发，认证链路写入）/
  `inactive`（长期未登录扫描写入）/ `manual`（管理员手动锁定）；活跃锁判定
  `unlock_at IS NULL AND (expire_at IS NULL OR expire_at > now)`。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_user` / `sys_account_lock`）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
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

UNLOCK_MODE_MANUAL = "manual"
"""解锁方式：管理员手动解锁。"""

UNLOCK_MODE_AUTO = "auto"
"""解锁方式：锁定到期自动解锁。"""

UNLOCK_MODES: tuple[str, ...] = (UNLOCK_MODE_MANUAL, UNLOCK_MODE_AUTO)
"""解锁方式取值清单。"""


class SysUser(BaseModel):
    """用户（系统账号，`sys_user`）：本地登录凭据与账号状态。"""

    __tablename__ = "sys_user"
    __table_args__ = (UniqueConstraint("username", "deleted_at", name="uq_sys_user_username_deleted_at"),)

    username: Mapped[str] = mapped_column(String(64), comment="登录账号（唯一；软删除后可复用）")
    password_hash: Mapped[str] = mapped_column(String(255), comment="口令哈希（PBKDF2 自描述串）")
    name: Mapped[str] = mapped_column(String(128), comment="用户昵称 / 显示名")
    status: Mapped[str] = mapped_column(String(16), default="enabled", comment="状态（enabled/disabled）")
    failed_count: Mapped[int] = mapped_column(Integer, default=0, comment="连续登录失败次数")
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="锁定到期时间（UTC；NULL=未锁）"
    )
    pwd_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="密码最近变更时间（UTC）")
    pwd_history: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="历史密码哈希（JSON 数组，仅应用侧读写；不参与库内检索）"
    )
    pwd_reset_required: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="是否需强制改密（登录超期置真，改密成功清假）"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近登录时间（UTC）")
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="邮箱（找回密码通道；维护入口归用户管理阶段）"
    )
    phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="手机号（找回密码通道；维护入口归用户管理阶段）"
    )
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="语言偏好（如 zh-cn）")
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="时区偏好（如 Asia/Shanghai）")


class SysAccountLock(BaseModel):
    """账号锁定记录（`sys_account_lock`）：锁定类型 / 原因 / 时间 / 期限 / 操作人与解锁信息。"""

    __tablename__ = "sys_account_lock"
    __table_args__ = (
        Index("idx_sys_account_lock_user_locked", "user_id", "locked_at"),
        Index("idx_sys_account_lock_user_unlock", "user_id", "unlock_at"),
        Index("idx_sys_account_lock_unlock_by", "unlock_by"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, comment="用户主键（逻辑外键 sys_user.id；同库）")
    lock_type: Mapped[str] = mapped_column(String(16), comment="锁定类型（fail_limit/inactive/manual）")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="锁定原因")
    locked_at: Mapped[datetime] = mapped_column(DateTime, comment="锁定时间（UTC）")
    locked_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="锁定操作人（inactive / fail_limit 系统触发为 NULL）"
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="锁定到期时间（UTC；NULL=需手动解锁）"
    )
    unlock_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="解锁时间（UTC；NULL=未解锁）")
    unlock_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="解锁操作人（自动解锁为 NULL）")
    unlock_mode: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="解锁方式（manual/auto；NULL=未解锁）"
    )
