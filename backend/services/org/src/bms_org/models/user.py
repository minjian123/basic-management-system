"""用户最小模型：`sys_user`（组织主数据服务租户库 `bms_org_{code}`）。

- 数据所有权：**组织主数据服务**（用户主数据写方唯一）；identity 经服务间契约调用内部凭据接口取数 / 写数，
  不直连本表。
- 本模型只承载**本地登录所需的最小字段**（账号 / 密码哈希 / 状态 / 最小锁定字段 / 密码策略字段 / 语言时区偏好）；
  完整用户档案与组织关系随用户管理阶段扩展。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_user`）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysUser(BaseModel):
    """用户最小模型（`sys_user`）：本地登录凭据与账号状态。"""

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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近登录时间（UTC）")
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="语言偏好（如 zh-cn）")
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="时区偏好（如 Asia/Shanghai）")
