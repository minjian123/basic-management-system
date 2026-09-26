"""会话记录模型：`sys_session`（认证与身份服务租户库 `bms_identity_{code}`）。

- 数据所有权：**认证与身份服务**（会话与身份映射表归 identity；`sys_user` 凭据主数据归 org）。
- 每条会话一行的登录态载体：登录写、刷新轮换更新 `refresh_token_hash`、登出 / 踢出置 `revoked_at`；
  运行时活跃标记另落 Redis（`bms:{租户}:sess:{session_id}`，TTL 与 refresh 对齐）。
- 表结构以《数据库设计》数据表文件为唯一事实源（`sys_session`）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from bms_core.models.base import BaseModel


class SysSession(BaseModel):
    """会话记录（`sys_session`）：登录会话载体与轮换 / 撤销依据。"""

    __tablename__ = "sys_session"
    __table_args__ = (
        UniqueConstraint("session_id", "deleted_at", name="uq_sys_session_session_id_deleted_at"),
        Index("idx_sys_session_user_id", "user_id"),
    )

    session_id: Mapped[str] = mapped_column(String(64), comment="会话 id（= JWT jti；与 id 同值）")
    user_id: Mapped[int] = mapped_column(BigInteger, comment="用户 ID（逻辑外键 → org 服务 sys_user.id）")
    refresh_token_hash: Mapped[str] = mapped_column(
        String(128), comment="refresh token 哈希（SHA-256 hex；不落原始值）"
    )
    device: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="设备标识（User-Agent 摘要）")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="登录 IP")
    login_at: Mapped[datetime] = mapped_column(DateTime, comment="登录时间（UTC）")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="refresh 过期时间（UTC）")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="撤销时间（UTC；NULL=有效）")
